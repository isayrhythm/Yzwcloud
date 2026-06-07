import { useState } from "react";
import { Button } from "tdesign-react";
import { useI18n } from "../i18n.jsx";

const PLANS = [
  {
    id: "trial",
    nameKey: "subscriptionTrialName",
    badgeKey: "subscriptionTrialBadge",
    descriptionKey: "subscriptionTrialDescription",
    prices: {
      monthly: "0",
      yearly: "0",
    },
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
    prices: {
      monthly: "480",
      yearly: "4,800",
    },
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
    prices: {
      monthly: "1,280",
      yearly: "12,800",
    },
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

export function SubscriptionPage({ onStart }) {
  const { t } = useI18n();
  const [billingCycle, setBillingCycle] = useState("yearly");
  const billingOptions = [
    ["monthly", t("subscriptionMonthly")],
    ["yearly", t("subscriptionYearly")],
  ];

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
          <div className="subscription-billing-toggle" role="group" aria-label={t("subscriptionBillingTitle")}>
            {billingOptions.map(([cycle, label]) => (
              <button
                aria-pressed={billingCycle === cycle}
                className={billingCycle === cycle ? "active" : ""}
                key={cycle}
                type="button"
                onClick={() => setBillingCycle(cycle)}
              >
                {label}
              </button>
            ))}
          </div>
          <small>{t("subscriptionBillingHint")}</small>
        </div>
      </section>

      <section className="subscription-plans" aria-label={t("subscriptionPlansTitle")}>
        {PLANS.map((plan) => {
          const isTrial = plan.id === "trial";
          const unitKey = isTrial
            ? "subscriptionTrialUnit"
            : billingCycle === "monthly"
              ? "subscriptionMonthUnit"
              : "subscriptionYearUnit";
          return (
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
                <strong>{plan.prices[billingCycle]}</strong>
                <em>{t(unitKey)}</em>
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
          );
        })}
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
