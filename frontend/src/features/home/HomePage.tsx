import { useMemo } from "react";
import { Link, Navigate } from "react-router";
import { useSamplePaper } from "../../app/queries.ts";
import { dark, light } from "../../diagram-engine/index.js";
import { useSession, useTheme } from "../../lib/store.ts";
import { diagramsFixture } from "../../test/fixtures.ts";
import { renderMethodologyDiagram } from "../diagrams/adapters.ts";
import styles from "./HomePage.module.css";

function EngineShowcase() {
  const theme = useTheme((state) => state.theme);
  const svg = useMemo(() => {
    const ir = diagramsFixture.methodology;
    if (!ir) return null;
    const result = renderMethodologyDiagram(ir, {
      theme: theme === "dark" ? dark : light,
      direction: "LR",
    });
    return result.ok ? result.svg : null;
  }, [theme]);
  if (!svg) return null;
  return (
    <figure className={styles.showcase} aria-label="Methodology diagram rendered by Bizora">
      <div dangerouslySetInnerHTML={{ __html: svg }} />
      <figcaption>
        Drawn live by Bizora&rsquo;s own diagram engine — every node traced to its
        paper.
      </figcaption>
    </figure>
  );
}

function SampleCta() {
  const sample = useSamplePaper();
  const to =
    sample.data?.available === true ? sample.data.workspace_path : "/papers";
  return (
    <Link to={to} className="bz-btn bz-btn-primary">
      Open the sample paper
    </Link>
  );
}

const STEPS = [
  {
    n: "01",
    title: "Upload",
    body: "Drop in a PDF, or paste an arXiv ID, DOI, or link. Bizora reads the full text and figures.",
  },
  {
    n: "02",
    title: "Extract",
    body: "Methodology, structure, and circuits come out as linked graphs — each node carrying its evidence.",
  },
  {
    n: "03",
    title: "Explore",
    body: "Walk the graph in 2D or 3D, ask the copilot, run what-ifs, and reproduce the build.",
  },
];

export function HomePage() {
  const { token } = useSession();
  if (token) return <Navigate to="/papers" replace />;
  return (
    <div className={`bz-page bz-enter ${styles.page}`}>
      <section className={styles.hero} aria-label="Welcome to Bizora">
        <div className={styles.heroCopy}>
          <p className={styles.kicker}>
            <span className={styles.rule} aria-hidden="true" />
            From paper to working graph
          </p>
          <h1>Turn scientific papers into explorable methodology graphs.</h1>
          <p className={styles.lede}>
            Bizora reads the papers, lifts out the method, and hands you
            something you can click, question, and rebuild — with every claim
            pinned to its source.
          </p>
          <div className={styles.ctas}>
            <SampleCta />
            <Link to="/login" className="bz-btn bz-btn-ghost">
              Log in
            </Link>
          </div>
        </div>
        <div className={styles.heroArt}>
          <img
            className="bz-art"
            src="/images/hero-papers.jpg"
            alt="Illustrated research papers covered in circuit traces and methodology graphs"
            loading="eager"
          />
          <p className={styles.caption}>Every node traced to its figure.</p>
        </div>
      </section>

      <section className={styles.steps} aria-label="How it works">
        {STEPS.map((step) => (
          <div key={step.n} className={styles.step}>
            <p className={styles.stepN}>{step.n}</p>
            <h2>{step.title}</h2>
            <p>{step.body}</p>
          </div>
        ))}
      </section>

      <EngineShowcase />

      <section className={styles.quality} aria-label="Extraction quality">
        <div>
          <h2>Measured, not promised</h2>
          <p>
            Extraction quality is scored against golden papers after every
            change — see the numbers before you trust a graph.
          </p>
        </div>
        <Link to="/quality" className="bz-btn bz-btn-ghost">
          See the eval scores
        </Link>
      </section>
    </div>
  );
}
