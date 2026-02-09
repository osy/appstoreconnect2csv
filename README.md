# App Store Connect Financial Reports to Gnucash

This script parses transactions (txt) and bank deposit information (csv) from App Store Connect and outputs split transactions for importing into Gnucash.

## Features

* Each transaction is split into commission (expense) and sale (income)
* Different currencies are placed into separate currency accounts
* Bank deposits are credited from each currency account and debited into "accounts receivable" in a split transaction with the correct currency conversion
* Date of the deposit is taken from the provided payment log file
* Exchange rates from each deposit statement is converted to a Gnucash rates list for more accurate day-to-day reports
* Taxes and adjustments are recorded in expenses

## Theory of Operation

One major challenge in handing taxes for App Store earnings is that Apple reports the revenue to the IRS through 1099-K and the profit to you in App Store Connect (as amount deposited to your bank account). This means that to get an accurate count of the App Store fees as an expense, you need to: get the total revenue for each currency, subtract the partner share, convert that to your bank currency, and sum up the total. This is further complicated by the fact that Apple provides the exchange rate used in a separate .csv which only lists the amount deposited to your bank account in the bank currency. We can use Gnucash to simplify the accounting and this script provides you with a tool to get started. The assumption is that the "Business" template is used in Gnucash as a starting point for the charter of accounts and a child account is created for each currency. Each App Store transaction first is credited from a sales account and is debited to an expense (commission) and asset (payment) account. This transaction takes place in the local currency. Next, data from the bank deposit .csv is parsed and a transaction is created crediting each payment account, exchanging it to the bank currency using Apple's exchange rate, and debited to the "accounts receivable" account. (Any adjustments and taxes are also handled here.) The user can then reconcile that with their bank account.

## Obtaining Reports

1. Visit [Payments and Financial Reports](https://appstoreconnect.apple.com/itc/payments_and_financial_reports#/) in App Store Connect
2. Select the month from the calendar
3. Click "Create Report" on the top right
4. Select "All Countries or Regions (Detailed)" and click "Create Report"
5. Download the .zip file and extract it to get the .txt report
6. Back on the website, click the Download button above "Proceeds" to download the payment .csv
7. Copy/paste the payment information into payment.log
8. Repeat steps 2-7 for any other month
9. Prepare a `payments.log` file containing the payment details (amount, account, units, date, transaction ID) for verification and dating.

## Generating CSV

Put all the .txt and .csv into a single directory and `cd` into that directory in Terminal. Then run:

`$ ./appstoreconnect2csv.py --payments payments.log *.txt *.csv`

And this will generate three files:

* `accounts.csv`: Import this into Gnucash with File -> Import -> Import Accounts from CSV..., this only needs to be done once or each time a new currency shows up
* `transactions.csv`: Import this into Gnucash with File -> Import -> Import Transactions from CSV..., make sure that "Multi-split" is checked
* `prices.csv`: Import this into Gnucash with File -> Import -> Import Prices from a CSV file... 

In the import options, the Date Format should be "m-d-y" and set "Leading Lines to Skip" (or "Number of Rows for the Header") to 1.

Note that each transaction needs a unique ID so the next ID is saved in "~/.config/appstoreconnect2csv_index".
