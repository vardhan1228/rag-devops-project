# Customer Data Protection and Retention

## What counts as sensitive

Customer data is classified into three tiers, and the tier decides where it may be
stored, who may see it, and how long it is kept.

**Restricted.** Identity document numbers, card numbers, card verification values,
personal identification numbers, passwords, one time passwords, biometric
templates, and full bank account numbers in combination with the holder's name.

**Confidential.** Name, address, contact details, balances, transaction history,
credit assessment outputs, and the contents of complaints.

**Internal.** Aggregated and anonymised figures where no individual is
identifiable, such as branch level deposit totals.

## Handling rules for restricted data

Card verification values are never stored after authorisation, in any system,
including logs. Personal identification numbers and passwords are never stored in
a recoverable form; only a salted hash is retained.

Card numbers are stored only as a token. Where a card number must be displayed it
is masked to the first six and last four digits. Full identity document numbers
are not retained at all; only the last four digits are held, sufficient to confirm
which document was verified.

Restricted data never appears in application logs, error messages, analytics
events, support tickets or test environments. Production data is not copied into a
test environment under any circumstances; test environments use generated data
only.

## Access control

Access follows least privilege and is granted by role, not by individual request.
A branch officer sees customers of their own branch. A contact centre agent sees
the customer they are currently serving, and that access is logged against the
call reference.

Access to the full customer base is limited to named roles in risk, audit and
compliance, and every such access is logged with the reason recorded at the time.
Bulk export requires approval from two officers, one of whom must be outside the
requesting function.

Every access to a customer record is logged with the identity of the accessor, the
timestamp and the purpose. Logs are immutable and retained for eight years. Staff
looking up their own record, a colleague's, or a public figure's without a service
reason is treated as misconduct, and the logs are reviewed for exactly this
pattern.

## Consent and purpose limitation

Data collected to open and operate an account may be used for that purpose and for
meeting legal obligations without separate consent. Any other use, in particular
marketing or sharing with group companies for cross-selling, requires explicit
opt-in consent recorded with a timestamp and the channel.

Consent is refusable and withdrawable, and service cannot be denied because a
customer refuses marketing consent. Withdrawal takes effect within seven working
days.

Customers registered on the do not disturb register receive no marketing
communication whatever internal consent records show.

## Sharing with third parties

Credit information is shared with the credit information companies as required by
law, monthly. Customers may obtain their own report directly from those companies,
once a year without charge.

Data is shared with a service provider only under a written agreement that limits
use to the specified service, prohibits onward transfer, requires deletion on
termination, and permits audit. The bank remains accountable for a provider's
handling of the data.

Disclosure to law enforcement requires written request under the relevant statutory
power, and is logged. Verbal requests are declined.

## Retention

| Record | Retention |
| --- | --- |
| Customer identification records | 10 years after relationship ends |
| Transaction records | 10 years from transaction |
| Records relating to a filed report | Until proceedings conclude |
| Access audit logs | 8 years |
| Video verification recordings | 10 years after relationship ends |
| Closed circuit television at branches | 90 days, longer if an incident is recorded |
| Call recordings, contact centre | 5 years |
| Marketing consent records | Life of relationship plus 3 years |

Retention periods are minimums set by regulation. Data is deleted once the longest
applicable period expires, and deletion is evidenced. Indefinite retention "just in
case" is not permitted, because data held is data that can be breached.

## Customer rights

A customer may obtain a copy of the personal data held about them, and may require
correction of anything inaccurate. Correction is applied within fifteen working
days and propagated to anyone the incorrect data was shared with, including the
credit information companies.

The right to erasure is limited: records the bank is required by law to retain
cannot be deleted on request, and a customer asking for erasure is told which
records must be kept and why.

## Breach response

A suspected breach is reported internally within one hour of detection. Assessment
of scope is completed within twenty-four hours. Regulatory notification follows the
timeline in the applicable direction, which for cyber incidents is six hours from
detection.

Affected customers are informed of what happened, which data was involved, what
the bank has done, and what the customer should do. Notification is not delayed
pending a complete investigation, since customers need to act while the risk is
live.
