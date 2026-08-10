"use client";

import { useEffect, useMemo, useState } from "react";

type PlanAnswers = {
  weight: number;
  goal: number;
  movement: "start" | "some" | "active";
  food: "all" | "green" | "flex";
  consideration: "none" | "knees" | "back";
};

type Tab = "today" | "week" | "food" | "progress";

const defaultAnswers: PlanAnswers = {
  weight: 112,
  goal: 10,
  movement: "start",
  food: "flex",
  consideration: "none",
};

const weekPlan = [
  { day: "Man", title: "Rolig gåtur", meta: "25 min · snakketempo", kind: "walk", icon: "↗" },
  { day: "Tir", title: "Styrke hjemme", meta: "20 min · hele kroppen", kind: "strength", icon: "+" },
  { day: "Ons", title: "Svømning", meta: "30 min · rolige baner", kind: "swim", icon: "≈" },
  { day: "Tor", title: "Restitutionsgåtur", meta: "20 min · helt roligt", kind: "walk", icon: "↗" },
  { day: "Fre", title: "Styrke hjemme", meta: "25 min · hele kroppen", kind: "strength", icon: "+" },
  { day: "Lør", title: "Længere gåtur", meta: "40 min · valgfri rute", kind: "walk", icon: "↗" },
  { day: "Søn", title: "Fri + bevægelighed", meta: "10 min · let og rart", kind: "rest", icon: "○" },
];

const meals = [
  { icon: "🥣", time: "Morgen", title: "Havregrød med skyr og bær", detail: "Havregryn · skyr · frosne bær · 1 spsk nødder", note: "Mætter godt og giver fuldkorn" },
  { icon: "🥪", time: "Frokost", title: "Rugbrød med æg og grønt", detail: "2 skiver rugbrød · 2 æg · tomat · agurk · gulerødder", note: "Nem at pakke og tage med" },
  { icon: "🍲", time: "Aften", title: "Kylling, kartofler og stor salat", detail: "1 håndflade protein · 1 knytnæve kartofler · ½ tallerken grønt", note: "Brug tallerkenmodellen—ingen vejning" },
  { icon: "🍎", time: "Hvis sulten", title: "Frugt + lille håndfuld nødder", detail: "Eller skyr, knækbrød eller grøntsagsstave", note: "Et forslag, ikke en pligt" },
];

function save(key: string, value: unknown) {
  if (typeof window !== "undefined") localStorage.setItem(key, JSON.stringify(value));
}

export default function Home() {
  const [screen, setScreen] = useState<"intro" | "quiz" | "plan">("intro");
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<PlanAnswers>(defaultAnswers);
  const [tab, setTab] = useState<Tab>("today");
  const [done, setDone] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const storedAnswers = localStorage.getItem("friform-answers");
    const storedDone = localStorage.getItem("friform-done");
    if (storedAnswers) {
      setAnswers(JSON.parse(storedAnswers));
      setScreen("plan");
    }
    if (storedDone) setDone(JSON.parse(storedDone));
  }, []);

  const completed = Object.values(done).filter(Boolean).length;
  const considerationText = answers.consideration === "knees" ? "knævenligt" : answers.consideration === "back" ? "rygvenligt" : "skånsomt";

  const startPlan = () => {
    save("friform-answers", answers);
    setScreen("plan");
    setTab("today");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const toggleDone = (id: string) => {
    const next = { ...done, [id]: !done[id] };
    setDone(next);
    save("friform-done", next);
  };

  const reset = () => {
    localStorage.removeItem("friform-answers");
    localStorage.removeItem("friform-done");
    setAnswers(defaultAnswers);
    setDone({});
    setStep(0);
    setScreen("intro");
  };

  return (
    <main className="app-shell">
      <Header screen={screen} onReset={reset} />
      {screen === "intro" && <Intro onStart={() => setScreen("quiz")} />}
      {screen === "quiz" && (
        <Quiz step={step} answers={answers} setAnswers={setAnswers} onBack={() => step === 0 ? setScreen("intro") : setStep(step - 1)} onNext={() => step === 4 ? startPlan() : setStep(step + 1)} />
      )}
      {screen === "plan" && (
        <Dashboard answers={answers} tab={tab} setTab={setTab} done={done} toggleDone={toggleDone} completed={completed} considerationText={considerationText} />
      )}
      <Footer />
    </main>
  );
}

function Header({ screen, onReset }: { screen: string; onReset: () => void }) {
  return (
    <header className="topbar">
      <button className="brand" onClick={() => window.location.reload()} aria-label="Fri Form forside">
        <span className="brand-mark"><i /></span><span>FRI FORM</span>
      </button>
      <div className="top-actions">
        <span className="free-badge"><i /> Altid gratis</span>
        {screen === "plan" && <button className="text-button" onClick={onReset}>Lav planen om</button>}
      </div>
    </header>
  );
}

function Intro({ onStart }: { onStart: () => void }) {
  return (
    <>
      <section className="hero">
        <div className="hero-copy">
          <div className="eyebrow"><span>100% gratis</span><span>Ingen konto</span><span>Ingen skam</span></div>
          <h1>En plan du faktisk<br /><em>kan leve med.</em></h1>
          <p className="lead">Små skridt til et lettere liv. Få en enkel ugeplan med almindelig mad, gåture, hjemmetræning og svømning—tilpasset dit udgangspunkt.</p>
          <button className="primary big" onClick={onStart}>Lav min gratis plan <span>→</span></button>
          <p className="microcopy">Tager ca. 2 minutter · Dine svar bliver på din enhed</p>
        </div>
        <div className="plan-preview" aria-label="Eksempel på en dagsplan">
          <div className="preview-top"><span>I DAG</span><span>2 af 4 klaret</span></div>
          <h2>Godmorgen 👋</h2>
          <p>Vi holder det enkelt i dag.</p>
          <div className="preview-task done-task"><span className="check">✓</span><div><b>Drik et glas vand</b><small>En blid start tæller også</small></div><time>08:00</time></div>
          <div className="preview-task"><span className="task-icon walk">↗</span><div><b>25 min. gåtur</b><small>Tempo: du kan stadig tale</small></div><time>17:00</time></div>
          <div className="preview-task"><span className="task-icon food">½</span><div><b>Halv tallerken grønt</b><small>Til dit aftensmåltid</small></div><time>Aften</time></div>
          <div className="pep"><span>✦</span><p><b>Det behøver ikke være perfekt.</b><br />Det skal bare være muligt igen i morgen.</p></div>
        </div>
      </section>

      <section className="trust-strip" aria-label="Fordele">
        <div><strong>0 kr.</strong><span>Nu og altid</span></div><div><strong>5 min.</strong><span>At komme i gang</span></div><div><strong>7 dage</strong><span>Én uge ad gangen</span></div><div><strong>Lokalt</strong><span>Data på din enhed</span></div>
      </section>

      <section className="how">
        <p className="section-kicker">EN PLAN, IKKE EN KUR</p>
        <h2>Hverdagen er svær nok.<br />Din plan skal være enkel.</h2>
        <div className="feature-grid">
          <article><span className="num">01</span><div className="feature-art plate"><i /><b /></div><h3>Spis almindelig mad</h3><p>Ingen forbudslister. Vi bruger portionsgreb og danske kostråd, så du kan handle i et helt almindeligt supermarked.</p></article>
          <article><span className="num">02</span><div className="feature-art route"><i /><b /><em /></div><h3>Bevæg dig på din måde</h3><p>Gåture, korte styrkepas og svømning. Planen starter roligt og bygger på, når kroppen er med.</p></article>
          <article><span className="num">03</span><div className="feature-art steps"><i /><b /><em /></div><h3>Se de små sejre</h3><p>Sæt flueben ved det, du gør. En mindre god dag nulstiller ikke din fremgang—du fortsætter bare.</p></article>
        </div>
      </section>

      <section className="start-banner">
        <div><span>KLAR, NÅR DU ER</span><h2>Dit første mål er ikke 20 kilo.<br />Det er den første uge.</h2></div>
        <button className="primary light" onClick={onStart}>Start helt gratis <span>→</span></button>
      </section>
    </>
  );
}

function Quiz({ step, answers, setAnswers, onBack, onNext }: { step: number; answers: PlanAnswers; setAnswers: (v: PlanAnswers) => void; onBack: () => void; onNext: () => void }) {
  const titles = ["Hvor starter vi?", "Hvad vil du først opnå?", "Hvordan bevæger du dig nu?", "Hvordan vil du helst spise?", "Skal planen tage særlige hensyn?"];
  const subs = ["Et cirka-tal er helt fint. Det bruges kun til at give din plan et realistisk udgangspunkt.", "Små, tydelige mål er lettere at holde fast i. Du kan altid ændre det senere.", "Vælg det, der ligner en normal uge—ikke din allerbedste uge.", "Der er ingen rigtig kost. Vælg den, der passer bedst til din hverdag.", "Hvis du har smerter eller sygdom, bør en sundhedsprofessionel hjælpe med at tilpasse motionen."];
  return (
    <section className="quiz-wrap">
      <div className="progress-head"><button onClick={onBack} aria-label="Gå tilbage">←</button><div><i style={{ width: `${(step + 1) * 20}%` }} /></div><span>{step + 1} / 5</span></div>
      <div className="quiz-card">
        <p className="section-kicker">DIN GRATIS PLAN</p><h1>{titles[step]}</h1><p className="quiz-sub">{subs[step]}</p>
        {step === 0 && <div className="weight-input"><label htmlFor="weight">Din vægt lige nu</label><div><input id="weight" inputMode="decimal" type="number" min="40" max="300" value={answers.weight} onChange={(e) => setAnswers({ ...answers, weight: Number(e.target.value) })} /><span>kg</span></div><small>Kun gemt lokalt på denne enhed</small></div>}
        {step === 1 && <Options value={String(answers.goal)} onChange={(v) => setAnswers({ ...answers, goal: Number(v) })} options={[{v:"5",t:"De første 5 kg",d:"Et nært og overskueligt mål"},{v:"10",t:"De første 10 kg",d:"Rolig fremgang over flere måneder"},{v:"15",t:"15 kg eller mere",d:"Vi deler rejsen op i mindre etaper"}]} />}
        {step === 2 && <Options value={answers.movement} onChange={(v) => setAnswers({ ...answers, movement: v as PlanAnswers["movement"] })} options={[{v:"start",t:"Jeg starter næsten fra nul",d:"Korte ture og ekstra blid styrke"},{v:"some",t:"Jeg bevæger mig lidt",d:"Nogle gåture eller aktivitet hver uge"},{v:"active",t:"Jeg er allerede ret aktiv",d:"Jeg vil have mere struktur"}]} />}
        {step === 3 && <Options value={answers.food} onChange={(v) => setAnswers({ ...answers, food: v as PlanAnswers["food"] })} options={[{v:"flex",t:"Fleksibelt og almindeligt",d:"Både kød, fisk og grønne retter"},{v:"green",t:"Mest vegetarisk",d:"Bælgfrugter, æg og mejeriprodukter"},{v:"all",t:"Jeg spiser det meste",d:"Giv mig den enkleste løsning"}]} />}
        {step === 4 && <Options value={answers.consideration} onChange={(v) => setAnswers({ ...answers, consideration: v as PlanAnswers["consideration"] })} options={[{v:"none",t:"Ingen særlige hensyn",d:"Rolig, almindelig opstart"},{v:"knees",t:"Jeg passer på mine knæ",d:"Mere svømning og færre dybe bøj"},{v:"back",t:"Jeg passer på min ryg",d:"Stabile, kontrollerede bevægelser"}]} />}
        <button className="primary full" onClick={onNext} disabled={step === 0 && (!answers.weight || answers.weight < 40)}> {step === 4 ? "Vis min ugeplan" : "Fortsæt"} <span>→</span></button>
        {step === 4 && <p className="safety-note">Planen er generel vejledning til raske voksne—ikke medicinsk behandling.</p>}
      </div>
    </section>
  );
}

function Options({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: { v: string; t: string; d: string }[] }) {
  return <div className="option-list">{options.map(o => <button key={o.v} className={value === o.v ? "selected" : ""} onClick={() => onChange(o.v)}><span className="radio"><i /></span><span><b>{o.t}</b><small>{o.d}</small></span></button>)}</div>;
}

function Dashboard({ answers, tab, setTab, done, toggleDone, completed, considerationText }: { answers: PlanAnswers; tab: Tab; setTab: (t: Tab) => void; done: Record<string, boolean>; toggleDone: (id: string) => void; completed: number; considerationText: string }) {
  const tabs = [{id:"today",label:"I dag",icon:"☀"},{id:"week",label:"Ugeplan",icon:"▦"},{id:"food",label:"Mad",icon:"◒"},{id:"progress",label:"Fremgang",icon:"↗"}] as const;
  return (
    <div className="dashboard">
      <aside className="side-nav">
        <p>MIN PLAN</p>{tabs.map(t => <button key={t.id} className={tab === t.id ? "active" : ""} onClick={() => setTab(t.id)}><span>{t.icon}</span>{t.label}</button>)}
        <div className="side-note"><b>Husk</b><p>En plan må gerne bøje. Den skal bare ikke knække.</p></div>
      </aside>
      <section className="dash-main">
        {tab === "today" && <Today done={done} toggleDone={toggleDone} completed={completed} answers={answers} considerationText={considerationText} setTab={setTab} />}
        {tab === "week" && <Week done={done} toggleDone={toggleDone} considerationText={considerationText} />}
        {tab === "food" && <Food />}
        {tab === "progress" && <Progress answers={answers} completed={completed} />}
      </section>
      <nav className="bottom-nav">{tabs.map(t => <button key={t.id} className={tab === t.id ? "active" : ""} onClick={() => setTab(t.id)}><span>{t.icon}</span>{t.label}</button>)}</nav>
    </div>
  );
}

function Today({ done, toggleDone, completed, answers, considerationText, setTab }: { done: Record<string, boolean>; toggleDone: (id: string) => void; completed: number; answers: PlanAnswers; considerationText: string; setTab: (t: Tab) => void }) {
  const tasks = [
    { id: "water", icon: "○", title: "Start med et glas vand", detail: "Når det passer ind i din morgen", color: "blue" },
    { id: "walk", icon: "↗", title: `${answers.movement === "start" ? 20 : 30} min. gåtur`, detail: `Roligt, ${considerationText} tempo`, color: "green" },
    { id: "plate", icon: "½", title: "Halv tallerken grønt", detail: "Til dit største måltid", color: "orange" },
    { id: "pause", icon: "✦", title: "2 minutters pause før ekstra", detail: "Mærk efter: sulten eller bare lyst?", color: "purple" },
  ];
  return <>
    <div className="dash-heading"><div><p className="section-kicker">DIN FØRSTE UGE</p><h1>I dag gør vi det<br />helt enkelt.</h1><p>Vælg det mulige frem for det perfekte.</p></div><div className="day-ring" style={{"--progress": `${Math.min(completed,4) * 25}%`} as React.CSSProperties}><div><b>{Math.min(completed,4)}</b><span>af 4</span></div></div></div>
    <div className="today-grid"><div className="task-list"><div className="list-head"><h2>Dagens små skridt</h2><span>{Math.min(completed,4)}/4 klaret</span></div>{tasks.map(task => <button key={task.id} className={`dash-task ${done[task.id] ? "done" : ""}`} onClick={() => toggleDone(task.id)}><span className={`task-bubble ${task.color}`}>{done[task.id] ? "✓" : task.icon}</span><span><b>{task.title}</b><small>{task.detail}</small></span><i className="task-check">{done[task.id] ? "✓" : ""}</i></button>)}</div>
      <aside className="today-side"><div className="meal-card"><div className="meal-visual"><span>½</span><i>¼</i><b>¼</b></div><p className="section-kicker">AFTENSMAD</p><h3>Kylling, kartofler<br />og sprød salat</h3><p>Ingen kalorietælling. Brug hånden og tallerkenen som guide.</p><button onClick={() => setTab("food")}>Se dagens mad <span>→</span></button></div><div className="quote-card"><span>“</span><p>Du er ikke bagud.<br />Du er i gang.</p></div></aside>
    </div>
    <div className="safety-bar"><span>i</span><p><b>Start roligt.</b> Stop ved smerter, svimmelhed eller ubehag. Har du diabetes, hjerteproblemer, markante ledsmerter eller medicin der påvirker vægten, så få lægen med på planen.</p></div>
  </>;
}

function Week({ done, toggleDone, considerationText }: { done: Record<string, boolean>; toggleDone: (id: string) => void; considerationText: string }) {
  return <><div className="dash-heading compact"><div><p className="section-kicker">UGE 1 · KOM GODT I GANG</p><h1>Din bevægelsesplan</h1><p>Ca. 170 minutter fordelt over ugen. Alt kan byttes rundt.</p></div></div><div className="week-list">{weekPlan.map((item, i) => { const id = `week-${i}`; return <button key={item.day} className={done[id] ? "done" : ""} onClick={() => toggleDone(id)}><span className="day-label">{item.day}</span><span className={`activity-icon ${item.kind}`}>{done[id] ? "✓" : item.icon}</span><span className="activity-copy"><b>{item.title}</b><small>{i === 0 ? item.meta.replace("snakketempo", considerationText + " tempo") : item.meta}</small></span><span className="week-check">{done[id] ? "Klaret" : "Markér"}</span></button>})}</div><div className="strength-box"><div><p className="section-kicker">20 MINUTTER · 2 RUNDER</p><h2>Dit hjemmepas</h2></div><div className="exercise-grid"><span><b>1</b>Rejs-sæt-dig fra stol<small>8 rolige gentagelser</small></span><span><b>2</b>Væg-armbøjninger<small>8–10 gentagelser</small></span><span><b>3</b>Stående træk med håndklæde<small>10 gentagelser</small></span><span><b>4</b>March på stedet<small>45 sekunder</small></span></div></div></>;
}

function Food() {
  return <><div className="dash-heading compact"><div><p className="section-kicker">MAD DER PASSER TIL ET LIV</p><h1>En enkel maddag</h1><p>Portionerne er pejlemærker. Spis langsomt, og stop når du er behageligt mæt.</p></div></div><div className="plate-rule"><div className="big-plate"><span>½<small>grønt</small></span><i>¼<small>protein</small></i><b>¼<small>kartofler<br />eller fuldkorn</small></b></div><div><p className="section-kicker">TALLERKENMODELLEN</p><h2>Du behøver ikke veje alt.</h2><p>Lad grøntsager fylde halvdelen, protein en fjerdedel og kartofler, ris, pasta eller brød den sidste fjerdedel. Tilføj lidt fedtstof og drik vand.</p></div></div><div className="meal-list">{meals.map(m => <article key={m.time}><span className="meal-emoji">{m.icon}</span><div><p>{m.time}</p><h3>{m.title}</h3><small>{m.detail}</small><em>{m.note}</em></div></article>)}</div><div className="shopping"><h2>En lille indkøbsliste</h2><div><span>Havregryn</span><span>Skyr</span><span>Rugbrød</span><span>Æg</span><span>Kylling eller bønner</span><span>Kartofler</span><span>Frosne grøntsager</span><span>Frugt</span></div></div></>;
}

function Progress({ answers, completed }: { answers: PlanAnswers; completed: number }) {
  const checkpoints = useMemo(() => [answers.weight, answers.weight - answers.goal / 3, answers.weight - answers.goal * 2 / 3, answers.weight - answers.goal], [answers]);
  return <><div className="dash-heading compact"><div><p className="section-kicker">FREMGANG UDEN PRES</p><h1>Se retningen,<br />ikke kun tallet.</h1><p>Vejning er valgfri. Energi, søvn og vaner er også fremgang.</p></div></div><div className="progress-cards"><article><span>✓</span><b>{completed}</b><p>små skridt klaret</p></article><article><span>↗</span><b>{answers.goal} kg</b><p>første langsigtede mål</p></article><article><span>○</span><b>7 dage</b><p>ad gangen</p></article></div><div className="journey"><div className="journey-head"><h2>Din vej i etaper</h2><span>Start: {answers.weight} kg</span></div><div className="journey-line">{checkpoints.map((n,i) => <div key={i} className={i === 0 ? "current" : ""}><i>{i === 0 ? "✓" : i}</i><b>{Math.round(n * 10) / 10} kg</b><small>{i === 0 ? "Her starter du" : i === 3 ? "Dit første mål" : "Mellemstation"}</small></div>)}</div></div><div className="checkin"><div><p className="section-kicker">UGENS CHECK-IN</p><h2>Hvad gik lidt lettere?</h2><p>Skriv det ned et sted du ser igen. Gentag det, der virkede—ikke nødvendigvis det hele.</p></div><span>✎</span></div></>;
}

function Footer() {
  return <footer><div className="footer-brand"><span className="brand-mark"><i /></span><b>FRI FORM</b><p>Gratis hjælp til små, holdbare skridt.</p></div><div><b>Fagligt grundlag</b><a href="https://foedevarestyrelsen.dk/kost-og-foedevarer/alt-om-mad/de-officielle-kostraad/kostraad-til-dig" target="_blank" rel="noreferrer">De officielle Kostråd</a><a href="https://www.sst.dk/vidensbase/forebyggelse/anbefalinger-om-fysisk-aktivitet/anbefalinger-om-fysisk-aktivitet-og-stillesiddende-tid/anbefalinger-om-fysisk-aktivitet-og-stillesiddende-tid-for-voksne-18-til-64-aar" target="_blank" rel="noreferrer">Sundhedsstyrelsens aktivitetsråd</a></div><div><b>Om tjenesten</b><p>Ingen konto. Ingen betaling. Dine valg gemmes kun lokalt i din browser.</p></div><small>© 2026 Fri Form · Generel information—ikke lægelig rådgivning.</small></footer>;
}
