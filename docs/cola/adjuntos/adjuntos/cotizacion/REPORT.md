# Competitive Research — Quotation & Proposal UX for DEKOPEN

**Task:** distill concrete design moves for DEKOPEN's commercial quotation (online proposal portal + PDF) from fenestration incumbents (Windowmaker, Orgadata Logikal), premium proposal tools (Qwilr, PandaDoc), and high-end trade/bespoke conventions. Goal: an offer document a manufacturer cannot fake in Canva/Word/PandaDoc — because it is generated from real engineering data, personalized to the actual openings, and interactive where it matters.

**Sources** (all public): Windowmaker 2025/2026 release notes + Windowmaker Web pages; Orgadata Logikal online help (Angebot/Kalkulation print options) and product pages; a real German fenestration offer PDF (msfaktura Musterangebot, 7 pp — attached); WindSketch, WinDoor Quote, PonudaPro marketing pages; Qwilr template/product/help pages; PandaDoc template gallery + help center; German AVLB/AGB documents from fenestration suppliers (Fieger, Muscheid, Lingel); proposal-writing guides (PandaDoc blog, Waco3, AnyGen, SiftHub).

Reference screenshots live in `./shots/` (captured from public marketing/docs pages only).

---

## 1. Cover-page patterns that work

The winning covers across PandaDoc's 167-template gallery and Qwilr's pages share one composition (see `shots/pandadoc-sales-template.png`, `shots/pandadoc-templates.png`, `shots/qwilr-sales-template.png`):

- **Full-bleed hero image, darkened ~40–60%, with the title typeset on it.** PandaDoc's top-rated sales proposal: tinted architectural photo, sender logo top-left, headline lower-left, "PREPARED BY / PREPARED FOR" name+company blocks at the bottom. That's the whole cover — nothing else.
- **Personalization tokens in the headline itself**: "Sales Proposal for [Client.Company]" — the client's name is the largest text on the page, not the vendor's.
- **Qwilr's cover is the same pattern as a web page**: media background (image or video), overlay title, and — critically — the pinned **Accept** button visible from the first viewport (top-right), plus a coachmark: "When you're ready, click 'Accept' to sign and accept this document."
- **Fenestration incumbent covers are weak**: the German Musterangebot (`shots/musterangebot-p1.png`) is a letterhead — logo top-center, sender block right, recipient block left, a metadata grid (Kundennummer, Angebotsnr., Datum, Sachbearbeiter + direct phone/email). Functional, but zero desire-signal. This is what DEKOPEN beats on page one.
- **What premium bespoke trade adds**: WindSketch (`shots/windsketch.png`) puts project identity + document state on the masthead: `RIVERSIDE RESIDENCE / Customer estimate · WS-1048 / [Customer ready]` and `PROFESSIONAL ESTIMATE — Valid for 10 days`. Document class + validity + a named project at the top edge — that's the trade equivalent of Qwilr's brand bar.

**Conventions to take:**
- One strong image beats any collage — and for DEKOPEN the strongest possible image is a **render/elevation of the customer's actual hero position** (largest glazed unit or front door), not stock photography. A Canva fake can't do that because it isn't generated.
- Headline = *project/customer name* ("Angebot – Neubau Musterstraße 12" / "Riverside Residence"), subline = scope summary ("8 Fenster · 2 Türen").
- Metadata as a small discrete block, not a wall: quote no., date, validity, sales contact *with a named human and direct line* (German buyers expect "Sachbearbeiter" — a person, not info@).
- Page identity strip on every PDF page: manufacturer wordmark + quote no. + date + "Seite X von Y". The Musterangebot does this; most SaaS templates don't.

## 2. Product / position presentation patterns

Fenestration offers are **position documents** — the unit of meaning is "opening" (room/elevation), not "SKU". The conventions that matter:

- **Drawing adjacent to spec, always.** Every serious tool puts the elevation sketch *next to* its construction spec — never an appendix of drawings. The Musterangebot: dimensioned interior-view sketch with opening-direction arrows on the left; "Konstruktion: Element-Außenmaße 1500×1100; Feld 1.1: Dreh-Kipp, DIN-Anschlag Links" on the right. Logikal lets the seller choose Innenansicht/Außenansicht and even Fluchttürgrafik. WindSketch expands a selected opening into drawing + spec table (Manufacturer / Series / Glass / Frame).
- **Positions grouped by the customer's geography**, not by product line: "01 Wohnzimmer", "02 Schlafzimmer" — room names the homeowner recognizes. Logikal additionally supports *Lose* (lots) with per-lot subtotals and optional page break per lot — the same idea for trade/contractor projects.
- **Sub-lines inside a position** carry the components: Fenster / Verglasung / Rollladen / Zubehör, each with quantity + unit (Stück, m², m) + price. This is the credibility layer — it's where engineering detail becomes commercial proof. DEKOPEN's BOM-driven data can render this natively; a Word fake has to type it.
- **Grouping identical units**: the convention is "3 Stück × 169,00 = 507,00" on one line — never repeat the card. A position card shows one drawing + spec, a quantity badge, unit price and line total. (Logikal's price-display modes: Einzelpreis + Elementstückpreis + Elementgesamtpreis — three levels of price depth for one element.)
- **Performance values are trust signals**: German offers print Glasanteil (% glass share), Gesamtenergiedurchlassgrad (g), Lichttransmissionsgrad (LT), Ug/Uw build-up ("Wärmeschutzglas U=0,7, Aufbau 4/12/4/12/4"). Spec-driven credibility — show them, don't bury them.
- **Windowmaker's direction** confirms the portal thesis: Smarter Quote ships an interactive web link (pricing, product details, terms, **3D view** of the design) instead of a static PDF, confirmable online and shareable over WhatsApp. The elevation/render isn't decoration — it's what customers use to verify they're buying the right thing.

## 3. Pricing presentation

- **Total as a band, not a cell.** WindSketch: dark full-width `PROJECT TOTAL $27,500` bar closing the estimate. The total gets visual weight no line item gets. Right below it: deposit schedule as three chips — `Deposit 50% / Progress 40% / Final 10%`.
- **"Investment" framing with a summary box.** Premium proposals lead pricing with an upfront investment summary (total, what's included, validity) *before* the itemized breakdown — buyers re-read the pricing page most; give them the number, then the structure. Never "POA".
- **Price depth is a commercial decision, not a bug.** Logikal's print options offer: full (Einzelpreis + Stückpreis + Gesamt), medium (Stückpreis + Gesamt), totals-only, hidden. B2B contractor quotes often show unit prices; homeowner offers often show only position totals. DEKOPEN should make this a per-document switch.
- **Discounts as explicit, labeled lines.** Logikal: Rabatt 1–4 as named percentage fields; PonudaPro: per-position *and* per-offer discounts. Showing "Project discount −5%" as its own line reads as generosity; hiding it reads as no discount. Also worth copying: Logikal's **Gesamtpreis override** — set a round target total and redistribute pro-rata across positions ("make it €24.900"), plus price-rounding modes. Ugly in the UI, beloved by salespeople.
- **Deposit/schedule in the quote body.** German trade terms (see AVLB sources): consumer Anzahlung up to ~50% is standard; progress payments keyed to milestones. Presenting the payment schedule *inside* the proposal (chips or mini-table, tied to totals) makes the money feel planned rather than demanded.
- **Tax handling**: B2B = net prices + "zzgl. gesetzl. MwSt."; consumers = gross end prices. One line of tax text per quote ("Alle Preise verstehen sich netto zzgl. 19 % USt." / "inkl. MwSt."), plus optional alternative-currency display (Logikal supports it). Explicitness prevents the classic dispute.
- **Validity next to money**: "Valid for 10 days" sits in WindSketch's masthead; construction-bid convention puts bid expiration at the top, near the price — not in the legal tail.

## 4. Alternatives / options comparison patterns

- **The German Alternativposition convention**: numbered as a sibling of the base position (`02a Schlafzimmer — Alternativposition`), with the explicit flag *"Diese Position ist nicht im Angebotspreis enthalten"* — full spec and price, excluded from the total by declaration, not by omission. Logikal makes alternatives a print-toggle.
- **Same-opening comparisons** work better than abstract tiers: for fenestration the meaningful comparison is variant-vs-variant on the *same* opening (PVC vs. aluminium, 2- vs. 3-glazing, standard vs. passivhaus threshold) — a two/three-column spec+price table anchored to the same drawing. The generic SaaS "Good/Better/Best with checkmarks" tier table is wrong here (see §7).
- **Interactive options in the portal**: PandaDoc's quote builder proves the pattern — optional line items the recipient can select/deselect, editable quantities, single- or multi-select groups, required vs. optional. Qwilr's interactive quote does the same with live repricing. For DEKOPEN: let the buyer toggle declared options (e.g. "Rollladen ja/nein", "Alternative: Aluminium") and see the total move — with the accepted configuration frozen into the order.
- **Show deltas, not just totals**: "+€3.120 vs. Basisposition" next to an alternative converts comparison into a decision. The Musterangebot era forces the buyer to do the subtraction; interactive tools removed that friction — DEKOPEN should too, in both PDF (printed delta) and portal (live delta).

## 5. Acceptance / decision UX — what makes approving feel safe

Qwilr's Accept Block is the reference implementation:

- **Persistent, explicit CTA**: pinned "Accept" affordance reachable from anywhere in the page, restated at the bottom after terms. Coachmark explains *what happens next* before the click — "click Accept to sign and accept this document". Removing mystery about the click is half the safety.
- **Accept presets by deal weight**: single-click accept, accept + one e-signature, accept + multiple signers, accept + payment. For a €25k window package, "e-sign + deposit in one flow" (Qwilr: "click, sign, done — from any device") is the premium close; Windowmaker's "Confirm Quote" button on the Smarter Quote link is the fenestration incumbent already doing it.
- **Freeze what was accepted**: Qwilr's post-accept screen states the acceptor's name/email/org and lets them save a copy of the acceptance. For DEKOPEN this should be the *revision hash*: the confirmation shows the exact spec set + total accepted, PDF regenerated/downloadable, proforma can auto-follow (PonudaPro does this).
- **Risk reducers adjacent to the button**: validity window, warranty/Guarantee line, named contact, delivery estimate, payment schedule — all within one viewport of Accept. Buyers approve when the last question is answered *next to* the button, not in a footnote.
- **Seller-side safety**: Qwilr notifies on view/sign/stall events; PandaDoc has audit trails and approval workflows; legal nuance from PandaDoc's own blog — a signature block can make the offer binding, so the acceptance copy should say exactly what the click means ("order confirmation follows / binding order now"). For German trade: offers are typically *freibleibend* until Auftragsbestätigung — the accept step should be labeled accordingly ("verbindliche Bestellung anfordern" vs. "Angebot annehmen").
- **Progress context**: WindSketch's `Estimate → Approval → Install scope` tracker tells the buyer where they are and what happens after yes. Cheap to build, big for confidence.

## 6. Terms / scope presentation

- **Two-layer terms**: a readable conditions block inside the proposal (validity, delivery estimate, payment schedule, price-adjustment note, warranty, what's included/excluded) + the full AGB/legal terms as appendix or linked page. The Musterangebot-era practice of printing AGB walls inline is what makes trade offers feel like invoices.
- **Scope clarity = dispute prevention**: construction-bid convention (AnyGen/Struvia) — explicit exclusions ("ohne Montage", "Fensterbänke nicht enthalten", "Gerüst/Elektro durch Auftraggeber") and assumptions get their own list, visibly, not folded into fine print. "Items NOT included" is a trust feature, not a concession.
- **Validity + price-escalation honesty**: German suppliers now carry explicit material-cost adjustment clauses (>10% input-cost movement → agreed adjustment mechanism). DEKOPEN copy should surface validity *and* the escalation rule in plain language near the price, since it protects the manufacturer AND reads as professional.
- **Legal identity in the footer, every page**: HRB/register/GF/Steuer-Nr./USt-IdNr + bank block — German convention buyers subconsciously check. Small type, consistent slot.
- **Named-human accountability**: Sachbearbeiter name + direct phone/email in the metadata block. Premium trade sells on "one team, one contact" (cf. Reeve & Co's architect-facing pitch); a faceless proposal from a manufacturer reads as a mass mailer.

## 7. What NOT to copy — generic SaaS proposal clichés

- **Video-background covers** (Qwilr's SaaS template): wrong register — a fenestration buyer wants their openings and the price, not a lifestyle loop. Use a project render.
- **ROI calculators**: meaningless for windows; substituting a fake "energy savings calculator" is equally risky unless computed honestly from U-values — if DEKOPEN does this, it must be engine-derived, labeled, and conservative.
- **Three-tier "Most Chosen" pricing tables**: SaaS anchoring pattern that doesn't map to fenestration alternatives (spec variants of the same opening ≠ package tiers). It reads as upsell pressure in a trade quote.
- **Stock-photo heroes, gradient blobs, abstract shapes**: exactly what Canva/Word produce; the premium signal is *generated* imagery of the actual units.
- **Stranger testimonials / logo walls** inside the quote: padding that delays the number. If social proof exists, it's a single line ("1.400 Installateure nutzen unser System") — or better, reference projects near the customer.
- **Feature-checklist green ticks**: spec bullets beat ✓-lists; the drawing is the checklist.
- **Webpage-with-no-document feel**: a quote portal that looks like a marketing landing loses the document's legal weight. Keep document affordances: quote number, page anatomy, PDF download, printable view.
- **POA / "request pricing"**: instant trust-killer; Waco3's data is blunt — never hide the number.
- **Vendor-first branding**: a proposal branded "DEKOPEN" instead of the manufacturer destroys the white-label value proposition (PonudaPro literally charges for un-watermarked branding — it's the premium feature).

## 8. Ranked design moves for DEKOPEN (PDF + portal)

Ranked by expected win-rate impact for a manufacturer competing against Canva/Word/PandaDoc output. Tag = mandate section.

1. **Hero = the project's own units.** Cover shows a generated elevation/render of the flagship position (or a clean grid of all positions) on the customer's project — impossible to fake without the engineering data. `[cover, products]`
2. **Interactive portal as the primary artifact; PDF as its printable shadow.** Accept link with product views (3D/rendered elevation), option toggles with live repricing, terms, and one-flow accept/e-sign — Windowmaker Smarter Quote parity minimum, Qwilr polish as the bar. `[portal, decision]`
3. **Position cards: drawing + spec adjacent, room/lot grouping, qty grouping.** One card per unique configuration ("×3 identical"), customer room names as group headers, component sub-lines (frame/glazing/shutter/accessory) with qty+unit+price, energy values (Uw, g, LT, Glasanteil) as a spec strip. `[products]`
4. **Total band + payment schedule chips + validity, one viewport.** Dark full-width totals bar ("Gesamt €24.900 netto"), deposit/progress/final milestone chips, "Angebot gültig bis TT.MM.JJJJ" immediately beside it. `[pricing, decision]`
5. **Named-human + project identity masthead.** `PROJECT NAME / Angebot Nº X / status` + Sachbearbeiter with direct phone/email; headline addresses the customer by name ("Prepared for"). `[cover, copy]`
6. **Price-depth modes per audience.** Switch: full unit pricing | position totals only | grand total only — manufacturer chooses per recipient (B2B dealer vs. homeowner vs. architect). `[pricing, pdf-scale]`
7. **Alternatives as first-class, marked siblings.** `Pos 02a — Alternative (nicht im Angebotspreis enthalten)` styling, per-opening variant comparison table, portal toggle with delta price; PDF prints the delta. `[alternatives, portal]`
8. **Explicit discount lines.** "Projektrabatt −5 %" as a visible line (optional per-position discounts); support Logikal-style round-total override with pro-rata redistribution in the authoring tool. `[pricing]`
9. **Plain-language terms block + full AGB appendix.** Included/excluded scope list, delivery estimate, payment terms, price-adjustment rule, warranty — bullets, not legalese; AGB as final page/link. `[terms, copy]`
10. **Frozen acceptance.** Accept click snapshots the revision; confirmation shows accepted scope + total + timestamp + acceptor; auto-issue PDF copy and optional proforma. `[decision, portal]`
11. **Document identity on every PDF page.** Manufacturer wordmark + Angebotsnr. + Datum + "Seite X von Y" + running carryover total (Übertrag); legal/bank footer. `[pdf-scale, white-label]`
12. **True white-label.** Manufacturer logo/colors/fonts/domain; zero DEKOPEN marks on customer surfaces. This alone beats "PandaDoc with a logo". `[white-label, portal]`
13. **German trade copy conventions.** "Angebot", salutation, freibleibend/binding wording chosen deliberately, Auftragsbestätigung flow language, correct net/gross tax phrasing per recipient type. `[copy, terms]`
14. **Positionsübersicht before detail.** A compact summary table (Pos | room | element | qty | total) ahead of the cards — the scannable page for the spouse/partner/architect who won't read detail. `[summary, pdf-scale]`
15. **Seller analytics.** View/open/section-engagement + stalled-accept notifications for the manufacturer (Qwilr-style) — invisible to the buyer, decisive for follow-up timing. `[portal]`
16. **Progress tracker.** `Angebot → Auftragsbestätigung → Produktion` status chip row in the portal — where am I, what's next. `[portal, decision]`
17. **Number hygiene everywhere.** Rounded totals option, consistent decimals, unit on every figure (m², m, Stück, €), no "ab"-pricing. `[copy, pricing]`
18. **Signature block that means what it says.** Name/title/date lines, company-stamp area, explicit statement of what acceptance triggers (binding order vs. request for order confirmation), e-sign optional. `[decision, terms]`

---

## Attachments index

| File | What it evidences |
|---|---|
| `fenster-musterangebot.pdf`, `shots/musterangebot-p1.png`, `shots/musterangebot-p2.png` | Real German fenestration offer: letterhead anatomy, room grouping, sketch+spec adjacency, component sub-lines, Positionssumme, Übertrag carryover, Alternativposition flag, legal/bank footer |
| `shots/windsketch.png` | Modern trade estimate: project masthead, validity chip, scope line, compact openings table, total band, deposit-schedule chips, progress tracker |
| `shots/orgadata-angebot.png` | Logikal offer-print options: discount fields, price-depth modes, alternatives toggle, sketch view choice, energy values, delivery date |
| `shots/qwilr-sales-template.png` | Qwilr: media cover + pinned Accept + sign-and-accept coachmark |
| `shots/pandadoc-templates.png`, `shots/pandadoc-sales-template.png` | PandaDoc cover conventions: full-bleed tinted hero, client-name headline, prepared-by/for blocks |
| `shots/windowmaker-web.png` | Windowmaker Web quoting UI (line price, qty, reference, render) |
| `shots/windoorquote.png` | WDQ: drawings-adjacent quoting UI marketed for on-site signing |
| `shots/logikal-en.png` | Logikal positioning: quote→build→produce, technical drawings as brand imagery |
