import { Button } from "tdesign-react";
import { useI18n } from "../i18n.jsx";

const PLANS = [
  {
    id: "trial",
    nameKey: "subscriptionTrialName",
    badgeKey: "subscriptionTrialBadge",
    descriptionKey: "subscriptionTrialDescription",
    price: "0",
    unitKey: "subscriptionTrialUnit",
    quotaKey: "subscriptionTrialQuota",
    ctaKey: "subscriptionTrialCta",
    features: [
      "subscriptionTrialFeature1",
      "subscriptionTrialFeature2",
      "subscriptionTrialFeature3",
      "subscriptionTrialFeature4",
    ],
  },
  {
    id: "lab",
    highlighted: true,
    nameKey: "subscriptionLabName",
    badgeKey: "subscriptionLabBadge",
    descriptionKey: "subscriptionLabDescription",
    price: "4,800",
    unitKey: "subscriptionYearUnit",
    quotaKey: "subscriptionLabQuota",
    ctaKey: "subscriptionLabCta",
    features: [
      "subscriptionLabFeature1",
      "subscriptionLabFeature2",
      "subscriptionLabFeature3",
      "subscriptionLabFeature4",
    ],
  },
  {
    id: "pro",
    nameKey: "subscriptionProName",
    badgeKey: "subscriptionProBadge",
    descriptionKey: "subscriptionProDescription",
    price: "12,800",
    unitKey: "subscriptionYearUnit",
    quotaKey: "subscriptionProQuota",
    ctaKey: "subscriptionProCta",
    features: [
      "subscriptionProFeature1",
      "subscriptionProFeature2",
      "subscriptionProFeature3",
      "subscriptionProFeature4",
    ],
  },
];

const METRICS = [
  ["subscriptionMetricAccounts", "3-30"],
  ["subscriptionMetricTasks", "100+"],
  ["subscriptionMetricStorage", "20GB+"],
  ["subscriptionMetricReports", "PDF / HTML"],
];

export function SubscriptionPage({ onStart }) {
  const { t } = useI18n();
  return (
    <main className="subscription-page shell">
      <section className="subscription-hero">
        <div className="subscription-hero-copy">
          <p className="eyebrow">YZW BioCloud SaaS</p>
          <h1>{t("subscriptionTitle")}</h1>
          <p>{t("subscriptionSummary")}</p>
        </div>
        <div className="subscription-billing-card" aria-label={t("subscriptionBillingTitle")}>
          <span>{t("subscriptionBillingTitle")}</span>
          <div className="subscription-billing-toggle" aria-hidden="true">
            <strong>{t("subscriptionMonthly")}</strong>
            <strong className="active">{t("subscriptionYearly")}</strong>
          </div>
          <small>{t("subscriptionBillingHint")}</small>
        </div>
      </section>

      <section className="subscription-metrics" aria-label={t("subscriptionMetricTitle")}>
        {METRICS.map(([labelKey, value]) => (
          <div key={labelKey}>
            <span>{t(labelKey)}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </section>

      <section className="subscription-plans" aria-label={t("subscriptionPlansTitle")}>
        {PLANS.map((plan) => (
          <article className={`subscription-plan ${plan.highlighted ? "highlighted" : ""}`} key={plan.id}>
            <div className="subscription-plan-head">
              <div>
                <span>{t(plan.badgeKey)}</span>
                <h2>{t(plan.nameKey)}</h2>
              </div>
              {plan.highlighted ? <strong>{t("subscriptionPopular")}</strong> : null}
            </div>
            <p>{t(plan.descriptionKey)}</p>
            <div className="subscription-price">
              <span>¥</span>
              <strong>{plan.price}</strong>
              <em>{t(plan.unitKey)}</em>
            </div>
            <div className="subscription-quota">{t(plan.quotaKey)}</div>
            <Button
              block
              shape="round"
              theme={plan.highlighted ? "primary" : "default"}
              variant={plan.highlighted ? "base" : "outline"}
              onClick={onStart}
            >
              {t(plan.ctaKey)}
            </Button>
            <ul>
              {plan.features.map((featureKey) => (
                <li key={featureKey}>{t(featureKey)}</li>
              ))}
            </ul>
          </article>
        ))}
      </section>

      <section className="subscription-detail-band">
        <div>
          <h2>{t("subscriptionScenarioTitle")}</h2>
          <p>{t("subscriptionScenarioText")}</p>
        </div>
        <div className="subscription-scenario-grid">
          <span>{t("subscriptionScenario1")}</span>
          <span>{t("subscriptionScenario2")}</span>
          <span>{t("subscriptionScenario3")}</span>
          <span>{t("subscriptionScenario4")}</span>
        </div>
      </section>
    </main>
  );
}
