# Synthetic Customer and Account Reference Data

**This data is entirely fabricated and exists only to exercise search.** No row
describes a real person. Names are placeholders, account numbers are masked to
the last four digits, and no identity document numbers, card numbers or
telephone numbers appear anywhere in this file. Do not copy this format into a
system that will hold real records without first applying the masking and access
controls described in the data protection note.

## Customer register

| Customer ID | Name | Segment | Risk category | Home branch | Relationship since |
| --- | --- | --- | --- | --- | --- |
| CUST-10042 | Customer A | Salaried | Low | Indiranagar | 2019-06-14 |
| CUST-10117 | Customer B | Self employed | Medium | Koramangala | 2021-02-03 |
| CUST-10238 | Customer C | Salaried, priority | Low | Whitefield | 2016-11-27 |
| CUST-10391 | Customer D | Small business | Medium | Jayanagar | 2022-08-19 |
| CUST-10455 | Customer E | Non resident | High | Indiranagar | 2020-01-09 |
| CUST-10502 | Customer F | Senior citizen | Low | Malleshwaram | 2014-04-22 |
| CUST-10614 | Customer G | Student | Low | Whitefield | 2024-07-01 |
| CUST-10733 | Customer H | Self employed, bullion trade | High | Chickpet | 2023-03-15 |

## Account register

| Account | Customer ID | Product | Balance | Status |
| --- | --- | --- | --- | --- |
| ****3317 | CUST-10042 | Regular Savings | 148,220 | Active |
| ****8842 | CUST-10042 | Fixed Deposit, 2 years | 500,000 | Active |
| ****2190 | CUST-10117 | Current Account | 63,410 | Active |
| ****7756 | CUST-10238 | Regular Savings | 1,204,880 | Active |
| ****7757 | CUST-10238 | Recurring Deposit, 36 months | 216,000 | Active |
| ****4028 | CUST-10391 | Current Account | 8,940 | Active, balance shortfall |
| ****6611 | CUST-10455 | Non Resident External Savings | 2,870,500 | Active |
| ****1903 | CUST-10502 | Regular Savings | 312,760 | Active |
| ****1904 | CUST-10502 | Fixed Deposit, 5 years, senior rate | 1,500,000 | Active |
| ****5570 | CUST-10614 | Basic Savings Bank Deposit | 4,310 | Active |
| ****9987 | CUST-10733 | Current Account | 1,942,300 | Under review |

## Loan register

| Loan | Customer ID | Product | Sanctioned | Outstanding | Rate | Status |
| --- | --- | --- | --- | --- | --- | --- |
| LN-55012 | CUST-10042 | Home loan | 4,200,000 | 3,610,400 | 8.65 percent floating | Regular |
| LN-55190 | CUST-10117 | Personal loan | 800,000 | 512,300 | 14.25 percent fixed | Regular |
| LN-55233 | CUST-10238 | Home loan | 9,500,000 | 6,980,100 | 8.40 percent floating | Regular |
| LN-55401 | CUST-10391 | Loan against property | 2,500,000 | 2,455,900 | 9.90 percent floating | Special mention, 44 days overdue |
| LN-55478 | CUST-10733 | Gold loan | 1,100,000 | 1,100,000 | 9.25 percent | Regular, loan to value 77 percent |
| LN-55520 | CUST-10614 | Education loan | 650,000 | 650,000 | 9.75 percent | Moratorium until course end |

## Illustrative alert queue

These are the monitoring alerts an analyst would be reviewing. Each records why
it fired and what the disposition was.

| Alert | Customer ID | Indicator | Detail | Disposition |
| --- | --- | --- | --- | --- |
| AL-8801 | CUST-10733 | Cash intensity | 11 cash deposits totalling 18.4 lakh in one month, bullion trade | Escalated, suspicious transaction report filed |
| AL-8802 | CUST-10391 | Structuring | Four deposits of 2.4 lakh each on consecutive days across two branches | Under review, source of funds requested |
| AL-8815 | CUST-10455 | High risk geography | Inbound wire from a flagged jurisdiction, 6.2 lakh | Closed, documented trade invoice supports the credit |
| AL-8820 | CUST-10117 | Pass-through | Credits of 9.1 lakh transferred out within 48 hours, residual balance 2,100 | Under review |
| AL-8834 | CUST-10042 | Profile inconsistency | Single credit of 12 lakh against declared income of 14 lakh per annum | Closed, proceeds of property sale evidenced |
| AL-8841 | CUST-10614 | Dormancy reversal | Account inactive 14 months, credit of 3.4 lakh received | Closed, education loan disbursement |

## Illustrative dispute queue

| Case | Customer ID | Type | Amount | Reported | Status |
| --- | --- | --- | --- | --- | --- |
| DS-2201 | CUST-10042 | Unauthorised card transaction | 34,990 | 2 days after alert | Shadow credit applied, third party breach |
| DS-2208 | CUST-10238 | Goods not received | 12,400 | 21 days after purchase | Chargeback raised, merchant response awaited |
| DS-2214 | CUST-10502 | Cash not dispensed at teller machine | 10,000 | Same day | Reversed on day 2, within deadline |
| DS-2219 | CUST-10117 | Credential sharing admitted | 78,500 | 9 days after alert | Customer liable, shadow credit reversed with notice |
| DS-2225 | CUST-10391 | Duplicate processing | 5,600 | 4 days | Resolved, network data conclusive |
| DS-2230 | CUST-10614 | Cancelled recurring payment | 1,299 | 11 days | Declined, merchant notice terms not met |

## Reading these tables

Balances are point in time as at 31 March 2026. Loan outstanding figures are
principal only and exclude accrued interest. Days overdue is counted from the
earliest unpaid instalment, not from the most recent one, which is why a single
missed instalment followed by partial payments can still show a large figure.
