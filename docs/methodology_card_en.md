# Methodology Passport Card

## 1. Project Information

| Field | Value |
|---|---|
| Title | Professional Burnout of Teachers in Private and State Schools: Group Comparison and the Role of Working Conditions |
| Authors | Zhanbolat Zhanat, Nurislam Yergali |
| GitHub repository | https://github.com/Zhanb089/teacher-burnout-study |

## 2. Research Type

**Quantitative** (cross-sectional, comparative, correlational).

We chose a quantitative design because our questions are about whether burnout levels are different and which working conditions are connected with burnout. Burnout is measured with a standard questionnaire, so every teacher gets a score. Working conditions are also numbers (hours, class size, ratings from 1 to 5). We compare two groups that already exist (state and private school teachers) using statistics. It is not an experiment, because we cannot randomly put teachers into schools. That is why we talk about associations and not about causes. We did not add interviews because our sample is small and we have limited time, and we mention this in the limitations.

## 3. Hypotheses

| Question | H0 (null) | H1 (alternative) |
|---|---|---|
| RQ1. Burnout level | There is no difference in burnout between state and private school teachers | Burnout levels differ between state and private school teachers. The main comparison is emotional exhaustion; depersonalization and personal accomplishment are secondary |
| RQ2, part a. Working conditions and burnout | None of the working conditions (working hours, class size, reporting, parental pressure, support, job stability) is related to emotional exhaustion | At least one of these working conditions is related to emotional exhaustion |
| RQ2, part b. School type when working conditions are controlled | The difference in burnout between school types does not become smaller when we control for working conditions | The difference in burnout between school types becomes smaller when we control for working conditions |
| RQ3. Different factors (exploratory) | The link between each factor and burnout is the same in both school types | In state schools class size and reporting are more strongly linked to burnout (H3a, H3b), in private schools parental pressure and job insecurity are (H3c, H3d) |

All tests are two-tailed (see section 5), so H1 for RQ1 and for RQ2a does not name a direction. From the job demands–resources model we expect that state school teachers have higher burnout and that more demands and fewer resources go together with higher burnout. A difference in the opposite direction would also go against H0. RQ2b is checked by comparing the school type coefficient (β) before and after working conditions are added to the regression, not by a separate significance test.

RQ3 is exploratory. With 15–20 teachers in each group we can only describe trends.

## 4. Variable Matrix

| Type | Variable | How it is measured |
|---|---|---|
| **Independent (IV)** | School type | 0 = state, 1 = private |
| | Workload | hours per week, including work at home |
| | Class size | average number of students |
| | Reporting | hours per week on reports and paperwork |
| | Support from colleagues and administration | average of 3–4 items, scale 1–5 |
| | Parental pressure | average of 3–4 items, scale 1–5 |
| | Job stability | average of 2–3 items, scale 1–5 |
| **Dependent (DV)** | Emotional exhaustion (EE) | sum of 9 items, 0–54 |
| | Depersonalization (DP) | sum of 5 items, 0–30 |
| | Reduced personal accomplishment (RPA) | sum of 8 items, 0–48 (lower score means stronger reduction) |
| | Total burnout index | z(EE) + z(DP) − z(RPA) |
| **Controlled (CV)** | Teaching experience | years |
| | Homeroom teacher | yes / no |
| | School level | primary / lower secondary / upper secondary |
| | Life load index (factors outside work) | sum score of the questionnaire block |
| **Fixed conditions** | Survey procedure | same questionnaire and instructions for all; Kazakh or Russian version; one way of sending the link; one collection period of 2–3 weeks (not at the end of term or during exams); one city; anonymous |
| **Fixed conditions** | Analysis environment | Python 3.11 with fixed library versions (requirements.txt, Dockerfile); fixed random seed; fixed sample file for testing the script |

## 5. Metrics and Baseline

**Primary metric:** emotional exhaustion score from the "Professional Burnout" questionnaire (MBI, adaptation by Vodopyanova and Starchenkova). To check the hypotheses we look at the difference between groups (Cohen's d) and at how strongly working conditions are linked to burnout (Spearman's ρ, β, ΔR²).

**Secondary metrics:** depersonalization, reduced personal accomplishment, total burnout index.

**Guardrail metrics:**

- Cronbach's alpha is 0.7 or higher for each scale;
- at least 15 complete questionnaires in each group;
- we record and report how many questionnaires were excluded;
- the two groups are similar on the control variables.

**Formulas:**

- d = (M_state − M_private) / SD_pooled
- ΔR² = R²(step 2) − R²(step 1)
- α = k/(k−1) · (1 − Σσᵢ² / σ²_total)

**Baseline:**

1. Reference group: state school teachers, because this is the most common type of school. Private school teachers are compared with them.
2. Norms: average scores from the authors of the questionnaire adaptation (EE 19.73; DP 7.78; RPA 32.93). We use them only for description, because they come from Russian samples.
3. Base model: a regression with only school type (step 1). We compare it with the model where working conditions are added (step 2).

**Analysis:** for RQ1 we use Welch's t-test, or the Mann–Whitney U test if the data are not normal. For RQ2a we use Spearman correlations, and for RQ2b hierarchical regression: we compare the school type β in step 1 and step 2 and look at ΔR². For RQ3 we use correlations inside each group. Significance level is 0.05, two-tailed. Hierarchical regression (β, ΔR²) is done in JASP. The script `src/benchmark.py` in our repository calculates the rest: scale scores, Cronbach's alpha, group comparison (Welch's t-test, U test, Cohen's d) and Spearman correlations.

## 6. Main Threats to Validity

| Threat | What we do about it |
|---|---|
| Teachers are not randomly assigned to schools (internal) | we talk only about associations; we control for experience, homeroom duties and school level |
| Effect of one particular school | we mention it in the limitations; we do not collect school names |
| Social desirability | the survey is anonymous and has a neutral title; we do not ask teachers directly if they have burnout |
| Small sample (30–40 teachers) | we report effect sizes and confidence intervals, not only p-values; RQ3 is exploratory |
| Self-selection, only one city (external) | we describe the sample; we do not generalise the results to the whole country |
| Norms are from Russian samples | we use burnout levels only for description and compare groups on raw scores |
