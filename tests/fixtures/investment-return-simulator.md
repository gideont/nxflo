# Build an Investment & Return Simulator

## 1. Product Vision

Build a modern, interactive financial planning application that allows individuals, entrepreneurs, investors, and small teams to model the potential financial outcome of a project or business opportunity **before committing resources**.

This is not a traditional expense tracker or accounting application.

It is a lightweight **FP&A and investment decision-support tool** that turns business ideas into measurable financial projections.

Core question:

**"If we invest this amount of money, time, and resources into an idea, what could we realistically expect in return, under what conditions, and over what timeframe?"**

The application should be generic enough to evaluate:

- An AI-generated YouTube channel
- A SaaS product or mobile application
- A consulting service
- An e-commerce business
- A small physical business
- A partnership between several investors
- An internal business improvement initiative

The main deliverable is a working, interactive prototype with a reusable financial model.

## 2. Core User Journey

Design the application around six steps.

### Step 1 — Define the investment opportunity

Allow the user to configure:

- Project name and description
- Business model and revenue model
- Project start date
- Financial forecast duration: 3, 6, 12, 24, or 36 months
- Currency: USD, CAD, etc.
- Participants, their responsibilities, and their contributions
- Initial investment budget
- Target return and acceptable maximum loss

Include a sample project: "Three Brothers AI Cartoon YouTube Channel".

### Step 2 — Model investment and operating costs

Allow users to add, modify, and remove cost items.

Support:

**Initial investment (CAPEX / startup costs)**

- Hardware and equipment
- Software setup
- Branding and design
- Development
- Marketing launch
- Other startup expenses

**Recurring operating expenses (OPEX)**

- AI API subscriptions
- Hosting and infrastructure
- Advertising
- Software subscriptions
- Freelance production
- Other operating costs

**Resource investment**

- Working hours per participant
- Estimated monetary value of each participant's time
- Expected hours per week or month

Distinguish cash expenditure from non-cash opportunity costs. Never count the same cost twice.

### Step 3 — Model revenue and business drivers

Revenue forecasts should be based on understandable business assumptions rather than arbitrary amounts.

Allow users to define revenue models such as:

- Advertising revenue
- Subscription revenue
- Product sales
- Consulting revenue
- Affiliate commissions
- Sponsorship income
- Custom revenue streams

Support driver-based calculations.

Example for an AI YouTube project:

Monthly revenue = (Monetized views / 1,000) × Revenue per 1,000 views + sponsorship + affiliate income.

Model the number of videos produced, average views, view growth, monetization eligibility, and production costs.

Do not assume that a new YouTube channel immediately earns advertising revenue. Allow zero revenue during the pre-monetization period.

For a SaaS project:

Monthly revenue = Active paying customers × Average monthly subscription fee.

Support customer acquisition, conversion rates, churn, and growth assumptions.

All assumptions must be editable and clearly explained.

### Step 4 — Scenario planning

Implement three investment scenarios:

1. Conservative — low revenue, slower adoption, potentially higher costs
2. Base Case — reasonable assumptions
3. Optimistic — higher revenue and faster growth

Users should be able to compare all three.

Add sensitivity analysis so users can adjust key variables and immediately see how financial outcomes change.

Examples:

- What if revenue is 50% lower than projected?
- What if operating expenses double?
- What if monetization is delayed six months?
- What if we reduce startup investment?
- How many customers or views are necessary to break even?

Include interactive sliders for important assumptions.

### Step 5 — Financial projections and investment analysis

Build a forecasting engine that generates monthly financial projections.

Calculate:

| Metric | Description |
|---|---|
| Initial investment | Upfront cash committed |
| Total investment | Initial and subsequent cash funding |
| Monthly revenue | Projected sales and income |
| Monthly operating costs | Recurring expenses |
| Operating profit | Revenue minus operating expenses |
| Net cash flow | Cash receipts minus cash payments |
| Cumulative cash flow | Accumulated cash position |
| Cash break-even | Month when cumulative project cash flow becomes non-negative |
| ROI | Net gain relative to invested capital |
| Payback period | Time required to recover investment |
| Maximum funding requirement | Peak cumulative cash deficit |
| NPV | Discounted value of future cash flows |
| IRR | Internal rate of return, where mathematically defined |

Use consistent financial definitions and show the calculation assumptions.

Treat financing contributions separately from project revenue and investor distributions separately from operating expenses.

Support a "never breaks even within the forecast period" result.

### Step 6 — Investment decision dashboard

Create a visually compelling executive dashboard.

Include:

- Investment required
- Total projected revenue
- Projected net profit or loss
- ROI percentage
- Expected payback period
- Maximum cash at risk
- Conservative / Base / Optimistic comparison

Create interactive charts:

1. Monthly revenue versus expenses — bar chart
2. Cumulative cash flow — line chart
3. Initial and recurring cost composition — donut chart
4. Three-scenario comparison — line chart
5. Break-even analysis — chart
6. ROI sensitivity heatmap
7. Investment contribution and return distribution by participant

Highlight the break-even month when it exists.

Make it easy to see what needs to happen for the investment to become profitable.

## 3. Investment Partnership Model

Support multiple participants contributing different resources.

For example:

- Partner A: $200 initial investment, strategy and technical support
- Partner B: Content production and creative direction
- Partner C: AI tools and video production

Allow participants to specify:

- Cash contribution
- Hours contributed
- Agreed value of work
- Ownership percentage
- Profit-sharing percentage
- Additional funding commitments

Cash contributions and work contributions should remain separate unless users explicitly agree to convert work into ownership.

Calculate each participant's expected cash distributions and investment return under each scenario.

Allow users to change the ownership and profit-sharing arrangements.

## 4. Budget vs. Actual Performance

After the investment begins, the model should support entering actual monthly financial results.

Compare:

- Budgeted versus actual spending
- Forecast versus actual revenue
- Expected versus actual operational KPIs
- Forecasted versus actual cumulative cash flow
- Revised break-even date

Allow the model to be reforecast based on actual performance.

Show whether the project is performing better or worse than the original investment assumptions.

Maintain an original baseline so users can see how expectations changed over time.

## 5. Investment Decision Framework

Include an optional decision framework to support rational investment decisions.

Users should define:

- Maximum initial investment
- Maximum acceptable loss
- Target ROI
- Evaluation period
- Minimum operational milestones

Example:

"Invest up to $500 for a 90-day YouTube pilot. Evaluate audience growth, production cost, and viewer retention. Continue only if agreed milestones are met."

Show a decision summary with:

- Potential upside
- Maximum modeled cash exposure
- Key assumptions
- Major risks
- Conditions required for success
- Suggested milestone checkpoints

Never present a financial forecast as a guaranteed outcome.

Distinguish the financial model's calculated outputs from subjective business judgments.

## 6. UI / UX Requirements

Build a polished, professional FP&A-style dashboard.

Design direction:

- Modern fintech / investment analytics aesthetic
- Clean, minimal, highly readable interface
- Professional typography
- Attractive charts and graphs
- Responsive desktop and mobile layout
- Clear distinction between editable assumptions and calculated results
- Immediate recalculation when assumptions change
- Tooltips explaining financial terminology

Provide these primary screens:

1. Project Overview
2. Investment & Resources
3. Revenue Assumptions
4. Scenario Planning
5. Financial Dashboard
6. Partnership Returns
7. Budget vs Actual

Users should be able to understand the financial model without accounting experience.

## 7. Prototype Technical Requirements

Build a functional prototype using:

- React and TypeScript
- Tailwind CSS
- Recharts for financial visualization
- Reusable financial calculation functions
- Browser localStorage for initial persistence
- JSON import/export for models and assumptions
- CSV export for monthly projections
- Printable executive summary

For the first prototype:

- No authentication required
- No external financial APIs required
- No payment integration
- No database required
- No AI API calls required
- All calculations should work locally
- Clearly label sample figures as hypothetical

Avoid unnecessary backend complexity.

Organize the calculation engine separately from UI components so that it can later be reused in a production application.

Ensure model formulas are testable and results are consistent across dashboards, tables, and exports.

## 8. Initial Demonstration Project

Preload an example based on three brothers exploring an AI-generated cartoon YouTube channel.

The objective is to determine whether investing a few hundred dollars could be worthwhile.

Demonstrate a 90-day experiment and a 12-month forecast.

Include hypothetical AI subscription expenses, video production costs, channel growth, YouTube advertising revenue, sponsorships, and contributor time.

Make the assumptions fully editable.

The demonstration should show both profitable and unprofitable scenarios rather than being artificially optimistic.

## 9. Definition of Done

The prototype is complete when a user can:

1. Create a new investment opportunity.
2. Enter the investment and operating assumptions.
3. Model potential revenues using business drivers.
4. Compare conservative, base, and optimistic outcomes.
5. Understand cash requirements, potential ROI, and payback time.
6. Visualize forecasts using interactive charts.
7. Model contributions and returns for multiple partners.
8. Save, reopen, and export the financial model.
9. Compare actual performance with the original forecast.
10. Use the result to make an informed go/no-go investment decision.

**Primary product principle:**

Do not build another budgeting app that merely tracks spending.

Build a financial decision simulator that helps users understand whether an idea is worth investing in, what assumptions must hold true, and what it would take to achieve a return.
