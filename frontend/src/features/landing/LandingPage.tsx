// Public presentation of the product that actually exists — every section is a
// real screen capture from the current build, every claim maps to a shipped
// feature. No demo request forms, no invented customers or numbers.

import { Link } from "react-router-dom";

import { t } from "../../i18n/es-CL";
import { DocLockup, Wordmark } from "../../brand";
import { Orb } from "../assistant/Orb";

import "./landing.css";

const SECTIONS: {
  key: "design" | "quote" | "produce" | "deliver";
  image: string;
  alt: string;
}[] = [
  { key: "design", image: "/landing/studio.webp", alt: t("landing.designAlt") },
  { key: "quote", image: "/landing/cotizacion.webp", alt: t("landing.quoteAlt") },
  { key: "produce", image: "/landing/plan-corte.webp", alt: t("landing.produceAlt") },
  { key: "deliver", image: "/landing/produccion.webp", alt: t("landing.deliverAlt") },
];

export function LandingPage(): JSX.Element {
  return (
    <main className="landing">
      <header className="landing-top">
        <span className="landing-brand">
          <Wordmark size={14} />
          <span className="brand-os">{t("app.brandOs")}</span>
        </span>
        <Link className="ui-button ui-button--primary" to="/login">
          {t("landing.enter")}
        </Link>
      </header>

      <section className="landing-hero">
        <div className="landing-hero__copy">
          <h1>{t("landing.heroTitle")}</h1>
          <p className="landing-hero__lead">{t("landing.heroLead")}</p>
          <div className="landing-hero__actions">
            <Link className="ui-button ui-button--primary" to="/login">
              {t("landing.enter")}
            </Link>
            <a className="ui-button" href="#producto">
              {t("landing.seeProduct")}
            </a>
          </div>
          <p className="landing-hero__note">
            <Orb size={20} title={t("landing.botName")} /> {t("landing.heroBot")}
          </p>
        </div>
        <figure className="landing-hero__shot">
          <img
            src="/landing/studio.webp"
            alt={t("landing.studioAlt")}
            width={1440}
            height={900}
            fetchPriority="high"
          />
          <figcaption>{t("landing.studioCaption")}</figcaption>
        </figure>
      </section>

      <section className="landing-sections" id="producto" aria-label={t("landing.productLabel")}>
        {SECTIONS.map((section, index) => (
          <article
            key={section.key}
            className={`landing-section${index % 2 ? " landing-section--flip" : ""}`}
          >
            <figure className="landing-section__shot">
              <img src={section.image} alt={section.alt} loading="lazy" />
            </figure>
            <div className="landing-section__copy">
              <h2>{t(`landing.${section.key}Title`)}</h2>
              <p>{t(`landing.${section.key}Body`)}</p>
            </div>
          </article>
        ))}
      </section>

      <section className="landing-assistant">
        <Orb size={44} title={t("landing.botName")} />
        <div>
          <h2>{t("landing.assistantTitle")}</h2>
          <p>{t("landing.assistantBody")}</p>
        </div>
        <figure className="landing-section__shot">
          <img src="/landing/asistente.webp" alt={t("landing.assistantAlt")} loading="lazy" />
        </figure>
      </section>

      <footer className="landing-foot">
        <DocLockup size={13} />
        <p>{t("landing.footer")}</p>
        <Link to="/login">{t("landing.enter")}</Link>
      </footer>
    </main>
  );
}
