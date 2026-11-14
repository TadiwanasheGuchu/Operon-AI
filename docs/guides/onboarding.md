# Getting started: connect Odoo and see your first insights

For a new organisation's owner or administrator. It takes about 15 minutes and needs no help
from engineering.

## 1. Create your organisation

1. Go to your Operon address and choose **Create an organisation**. Enter your name, work email,
   a password (at least 12 characters; a passphrase works well) and the organisation name.
2. Confirm your email from the link we send, then sign in.
3. Recommended: turn on two-factor authentication under **Account → Security**.

You are the organisation's **owner**. Invite colleagues later from **Members** (see the
[administration guide](administration.md)).

## 2. Prepare Odoo

Operon reads inventory, sales and purchasing data from Odoo. It writes only one thing: draft
requests for quotation, and only after a purchase request has been approved in Operon.

In Odoo (versions 17, 18 or 19), with the Inventory, Sales and Purchase apps installed:

1. Create a user for Operon, for example *Operon integration*. Give it read access to
   Inventory, Sales and Purchase, and *User* rights in Purchase so it can create RFQs.
2. Signed in as that user, go to **Preferences → Account Security → New API Key**, name it
   *Operon*, and copy the key. Odoo shows it once.
3. Note your Odoo address (for example `https://acme.odoo.com`) and the database name. The
   database name is shown on the Odoo database selector, or ask your Odoo administrator.

Operon must be able to reach your Odoo address over HTTPS from the internet. Private network
addresses are refused for security.

## 3. Connect Odoo in Operon

1. Open **Integrations** and choose **Connect Odoo**.
2. Fill in:
   - **Name in Operon:** for example *Odoo production*.
   - **Url:** your Odoo address.
   - **Database:** the database name.
   - **Username:** the Operon user's login.
   - **Api key:** the key from step 2. It is encrypted and never shown again.
   - **Api version:** leave it on *auto*.
   - **Sync every:** 15 minutes is a good start.
3. Choose **Test and connect**. Operon checks that it can sign in, that the apps it needs are
   installed, and which API Odoo offers. If something is missing, the message says what.

The first sync starts straight away. It brings in locations, products, suppliers and their
terms, stock levels, the last 90 days of sales, and open purchase orders. The connection page
shows progress and a history of every sync, with counts and any errors.

## 4. See your first insights

When a sync finishes, Operon runs its detectors.

- **Stockout risk:** products whose stock, plus what's on order, won't cover expected sales
  within the supplier's lead time and the safety buffer.
- **Overdue purchase orders:** orders past their expected date and not yet received.

Open **Intelligence**. Each insight shows:

- what was detected;
- the evidence: stock, sales rate and open orders, each linked to its source record and sync;
- why it matters;
- a recommended action;
- the assumptions behind it.

The **Overview** gives the organisation-wide picture, and every figure says where it comes from.

To tune detection, for example the safety buffer or minimum severity, go to
**Intelligence → Settings**.

## 5. Act on an insight

From a stockout-risk insight, choose **Create purchase request**. The request follows your
approval policy (**Purchase requests → Settings**): for example, one approval below a value and
two above it. Nobody can approve their own request. Once approved, Operon creates a draft RFQ in
Odoo, and the request's history records every step.

## Optional next steps

- **AI explanations and the assistant:** **Intelligence → Settings → AI**. Off by default. Set a
  monthly token budget.
- **Single sign-on:** see the [administration guide](administration.md#single-sign-on).
- **No Odoo?** Use **Integrations → Set up CSV import**, or connect Shopify.

## If something goes wrong

| You see | Do this |
|---|---|
| "Odoo rejected the username or API key." | Check the database name, the login and the API key; the key belongs to that user |
| "Odoo's Inventory app isn't installed for this database…" | Install Inventory (and Sales, Purchase) on that database |
| "That address points to a private network, which isn't allowed." | Use the public HTTPS address of your Odoo, not an internal one |
| Sync failing | Open the connection; the latest sync shows the error and the record it stopped at |
| No insights after a sync | Nothing is at risk under the current settings. Check **Intelligence → Settings**, and the detection runs list for counts |
