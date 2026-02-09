#!/usr/bin/env python3

import os
from datetime import datetime
from decimal import Decimal
from collections import namedtuple
from datetime import datetime
import calendar
import re
import csv

CurrencyData = namedtuple("CurrencyData", [
    "currency", "earned", "input_tax", "adjustments", "witholding", "total", "exchange_rate", "proceeds", "bank_currency"
])

Transaction = namedtuple("Transaction", [
    "date", "entries"
])

Report = namedtuple("Report", [
    "currencies", "transactions", "start_date", "end_date"
])

Payment = namedtuple("Payment", [
    "bank_currency", "transactions", "conversion", "amount", "estimated_date"
])

PaymentLogEntry = namedtuple("PaymentLogEntry", [
    "amount", "currency", "account_name", "units_sold", "date", "transaction_id"
])

INDEX = 0

def get_estimated_date(input_string):
    # Extract the month and year using regex
    match = re.search(r'\((\w+),\s(\d{4})\)', input_string)
    if match:
        month_name, year = match.groups()
        # Convert month name to month number
        month = datetime.strptime(month_name, "%B").month
        year = int(year)
        # Return first day of the month
        return datetime(year, month, 1)
    else:
        return None

def parse_payment_log(file_name):
    entries = []
    with open(file_name, 'r') as f:
        content = f.read().strip()
    
    # Split by double newlines to separate blocks
    blocks = re.split(r'\n\s*\n', content)
    
    for block in blocks:
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        if len(lines) < 6:
            continue
            
        # Line 1: Amount + Currency (e.g., "22,070.60 USD")
        amount_parts = lines[0].split(' ')
        amount = Decimal(amount_parts[0].replace(',', ''))
        currency = amount_parts[1] if len(amount_parts) > 1 else ""
        
        # Line 2: Account Name
        account_name = lines[1]
        
        # Line 3: Units Sold
        units_sold = int(lines[2].replace(',', ''))
        
        # Line 4: Units Sold Label (ignore)
        
        # Line 5: Payment Date
        date_str = lines[4]
        try:
            date = datetime.strptime(date_str, "%B %d, %Y").strftime("%m/%d/%Y")
        except ValueError:
             # Fallback or error handling if date format varies
            date = date_str

        # Line 6: Transaction ID
        transaction_id = lines[5].replace("Transaction ID: ", "")
        
        entries.append(PaymentLogEntry(
            amount=amount,
            currency=currency,
            account_name=account_name,
            units_sold=units_sold,
            date=date,
            transaction_id=transaction_id
        ))
    return entries

def parse_payment_csv(file_name):
    global INDEX
    payments = []
    with open(file_name, newline='') as csvfile:
        reader = csv.reader(csvfile)
        first_row = next(reader)
        if not first_row[0].startswith('iTunes Connect - Payments and Financial Reports'):
            print(f"Ignoring unknown file {file_name}")
            return []
        
        estimated_date_dt = get_estimated_date(first_row[0])
        assert estimated_date_dt, "Could not parse date from header"
        # We store the datetime object for comparison, but convert to string for Transaction if needed?
        # Transaction expects a string date in MM/DD/YYYY format usually based on previous code.
        # Let's check Transaction usage. It expects string.
        date = estimated_date_dt.strftime("%m/%d/%Y")

        for line in reader:
            if line[0] != 'Country or Region (Currency)':
                continue
            currency_list = []
            for line in reader:
                if line[0] == '':
                    break
                if line[8] == '':
                    continue
                currency_list.append(CurrencyData(
                    currency = re.search(r"\((\w{3})\)", line[0]).group(1),
                    earned = Decimal(line[2]),
                    input_tax = Decimal(line[4]),
                    adjustments = Decimal(line[5]),
                    witholding = Decimal(line[6]),
                    total = Decimal(line[7]),
                    exchange_rate = Decimal(line[8]),
                    proceeds = Decimal(line[9]),
                    bank_currency = line[10]
                ))

            if not currency_list:
                continue

            amount = Decimal(next((s for s in next(reader) if s.strip()), None).split(' ')[0].replace(',', ''))
            calculated_amount = sum(v.proceeds for v in currency_list)
            assert calculated_amount == amount, "Total proceeds do not match, there must be a parsing error"
            
            account = next((s for s in next(reader) if s.strip()), None)

            data = []
            conversion = []
            bank_currency = None
            data.append([date, f"Assets:Accounts Receivable", amount, INDEX, account, '', 0])
            for currency_data in currency_list:
                real_exchange_rate = currency_data.proceeds / currency_data.total # this is more accurate
                data.append([date, f"Assets:App Store Payments:{currency_data.currency}", -currency_data.total, INDEX, account, '', real_exchange_rate])
                if currency_data.currency != currency_data.bank_currency:
                    conversion.append([date, currency_data.exchange_rate, 'CURRENCY', currency_data.currency, currency_data.bank_currency])
                if bank_currency == None:
                    bank_currency = currency_data.bank_currency
                else:
                    assert bank_currency == currency_data.bank_currency, "Multiple bank currencies detected, not supported"
            INDEX += 1

            # taxes and adjustments
            for currency_data in currency_list:
                taxes = currency_data.input_tax + currency_data.witholding
                adjustments = currency_data.adjustments
                if taxes + adjustments == 0:
                    continue
                real_exchange_rate = currency_data.proceeds / currency_data.total # this is more accurate
                if taxes != 0:
                    data.append([date, "Expenses:Taxes:Other Tax", -taxes * real_exchange_rate, INDEX, f'{currency_data.currency} Taxes and Adjustments', 'Tax', 0])
                if adjustments != 0:
                    data.append([date, "Expenses:Adjustment", -adjustments * real_exchange_rate, INDEX, f'{currency_data.currency} Taxes and Adjustments', 'Adjustment', 0])
                data.append([date, f"Assets:App Store Payments:{currency_data.currency}", taxes + adjustments, INDEX, f'{currency_data.currency} Taxes and Adjustments', '', real_exchange_rate])
                INDEX += 1

            payments.append(Payment(
                bank_currency = bank_currency,
                transactions = [Transaction(date, data)],
                conversion = conversion,
                amount = amount,
                estimated_date = estimated_date_dt
            ))
    return payments

def parse_app_store_connect_report(file_name):
    global INDEX
    all_data = []
    transactions = []
    currencies = set()

    with open(file_name, 'r') as file:
        lines = file.readlines()

    # Extract the header and data rows
    start_date = lines[1].strip().split('\t')[1]
    end_date = lines[2].strip().split('\t')[1]
    header_line = lines[3].strip().split('\t')
    data_lines = lines[4:]

    # Parse the data lines and append to all_data
    for line in data_lines:
        row = line.split('\t')
        if row[0] == 'Country Of Sale':
            break
        all_data.append(row)

    # Sort all data by Transaction Date (assume 0-based index for the date column)
    settlement_date_index = header_line.index('Settlement Date')
    title_index = header_line.index('Title')
    quantity_index = header_line.index('Quantity')
    partner_share_index = header_line.index('Partner Share')
    partner_share_currency_index = header_line.index('Partner Share Currency')
    customer_price_index = header_line.index('Customer Price')
    customer_currency_index = header_line.index('Customer Currency')

    for line in all_data:
        settlement_date = line[settlement_date_index]
        title = line[title_index]
        quantity = int(line[quantity_index])
        partner_share = Decimal(line[partner_share_index])
        partner_share_currency = line[partner_share_currency_index]
        customer_price = Decimal(line[customer_price_index])
        customer_currency = line[customer_currency_index]
        assert partner_share_currency == customer_currency, "Unsupported currency conversion"
        currencies.add(customer_currency)
        customer_total = abs(customer_price) * quantity
        partner_total = abs(partner_share) * quantity
        commission = (abs(customer_price) - abs(partner_share)) * quantity

        data = []
        data.append([settlement_date, f"Income:Sales:{customer_currency}", -customer_total, INDEX, title, '', 0])
        data.append([settlement_date, f"Assets:App Store Payments:{customer_currency}", partner_total, INDEX, title, '', 0])
        data.append([settlement_date, f"Expenses:Commissions:{customer_currency}", commission, INDEX, title, 'Commission', 0])
        transactions.append(Transaction(settlement_date, data))
        INDEX += 1

    return Report(
        currencies = currencies,
        transactions = transactions,
        start_date = start_date,
        end_date = end_date
    )

def write_accounts(output_csv, target_currency, currencies):
    currencies = sorted(currencies)
    with open(output_csv, 'w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(['Type','Full Account Name','Account Name','Account Code','Description','Account Color','Notes','Symbol','Namespace','Hidden','Tax Info','Placeholder'])
        csv_writer.writerow(['RECEIVABLE','Assets:Accounts Receivable','Accounts Receivable','','Accounts Receivable','','',target_currency,'CURRENCY','F','F','F'])
        csv_writer.writerow(['ASSET',f'Assets:App Store Payments','App Store Payments','','App Store Payments','','',target_currency,'CURRENCY','F','F','T'])
        csv_writer.writerow(['EXPENSE','Expenses:Adjustment','Adjustment','','Adjustment','','',target_currency,'CURRENCY','F','F','F'])
        csv_writer.writerow(['EXPENSE','Expenses:Taxes:Other Tax','Other Tax','','Other Tax','','',target_currency,'CURRENCY','F','F','F'])
        csv_writer.writerow(['EXPENSE','Expenses:Commissions','Commissions','','Commissions','','',target_currency,'CURRENCY','F','F','F'])
        csv_writer.writerow(['INCOME','Income:Sales','Sales','','','','',target_currency,'CURRENCY','F','F','T'])
        for currency in currencies:
            csv_writer.writerow(['ASSET',f'Assets:App Store Payments:{currency}',currency,'','','','',currency,'CURRENCY','F','F','F'])
            csv_writer.writerow(['EXPENSE',f'Expenses:Commissions:{currency}',currency,'','','','',currency,'CURRENCY','F','F','F'])
            csv_writer.writerow(['INCOME',f'Income:Sales:{currency}',currency,'','','','',currency,'CURRENCY','F','F','F'])
        print(f"Accounts successfully written to {output_csv}")

def write_transactions(output_csv, transactions):
    transactions = sorted(transactions, key=lambda x: datetime.strptime(x.date, '%m/%d/%Y'))
    data = [entry for transaction in transactions for entry in transaction.entries]
    with open(output_csv, 'w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(['Date', 'Account', 'Amount', 'Number', 'Description', 'Memo', 'Price'])
        csv_writer.writerows(data)
        print(f"Data successfully written to {output_csv}")

def write_prices(output_csv, conversions):
    conversions = sorted(conversions, key=lambda x: datetime.strptime(x[0], '%m/%d/%Y'))
    with open(output_csv, 'w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(['Date', 'Amount', 'From Namespace', 'From Symbol', 'Currency To'])
        csv_writer.writerows(conversions)
        print(f"Rates successfully written to {output_csv}")

if __name__ == "__main__":
    import sys
    
    config_file = os.path.join(os.path.expanduser("~"), ".config", "appstoreconnect2csv_index")
    if os.path.exists(config_file):
        with open(config_file, "r") as file:
            INDEX = int(file.read().strip())

    if len(sys.argv) < 3:
        print("Usage: python3 appstoreconnect2csv.py [--payments payments.log] file1.[txt|csv] file2.[txt|csv] ...")
    else:
        args = sys.argv[1:]
        payment_log_file = None
        if "--payments" in args:
            try:
                idx = args.index("--payments")
                if idx + 1 < len(args):
                    payment_log_file = args[idx+1]
                    # Remove --payments and its argument from args
                    args.pop(idx)
                    args.pop(idx)
                else:
                    print("Error: --payments requires a file argument")
                    sys.exit(1)
            except ValueError:
                pass

        file_names = args
        currencies = set()
        target_currency = None
        transactions = []
        conversions = []
        remaining_files = []
        
        # first parse the txt files
        for file_name in file_names:
            if not file_name.endswith('.csv'):
                report = parse_app_store_connect_report(file_name)
                currencies |= report.currencies
                transactions += report.transactions
            else:
                remaining_files.append(file_name)
        
        parsed_payments = []
        if payment_log_file:
            parsed_payments = parse_payment_log(payment_log_file)

        # next parse the csv files
        all_csv_payments = []
        for file_name in remaining_files:
            all_csv_payments.extend(parse_payment_csv(file_name))

        if parsed_payments:
            for payment in all_csv_payments:
                matched_entry = None
                for i, entry in enumerate(parsed_payments):
                    try:
                        entry_date = datetime.strptime(entry.date, "%m/%d/%Y")
                    except ValueError:
                        continue 
                    
                    # Match if amount matches and payment date is strictly after the estimated date (start of earnings month)
                    if entry.amount == payment.amount and entry_date > payment.estimated_date:
                        matched_entry = entry
                        parsed_payments.pop(i)
                        break
                
                if matched_entry:
                    new_date_str = matched_entry.date
                    
                    # Rebuild transactions with new date
                    for t in payment.transactions:
                        new_entries = []
                        for row in t.entries:
                            new_row = list(row)
                            new_row[0] = new_date_str
                            new_entries.append(new_row)
                        transactions.append(Transaction(new_date_str, new_entries))
                    
                    # Rebuild conversions with new date
                    for c in payment.conversion:
                        new_c = list(c)
                        new_c[0] = new_date_str
                        conversions.append(new_c)

                    if target_currency == None:
                        target_currency = payment.bank_currency
                    else:
                        assert target_currency == payment.bank_currency, "Multiple bank currencies detected, not supported"

                else:
                    print(f"Error: Could not find matching payment for amount {payment.amount} after {payment.estimated_date}")
                    sys.exit(1)
        else:
            # Fallback if no payment log provided: use estimated dates
            for payment in all_csv_payments:
                transactions += payment.transactions
                conversions += payment.conversion
                if target_currency == None:
                    target_currency = payment.bank_currency
                else:
                    assert target_currency == payment.bank_currency, "Multiple bank currencies detected, not supported"

        write_accounts('accounts.csv', target_currency, currencies)
        write_transactions('transactions.csv', transactions)
        write_prices('prices.csv', conversions)

        os.makedirs(os.path.dirname(config_file), exist_ok=True)
        #with open(config_file, "w") as file:
        #    file.write(str(INDEX))
