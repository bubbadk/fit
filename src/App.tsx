import { FormEvent, useEffect, useMemo, useState } from "react";

type User = { name: string; email: string };
type Meal = { title: string; ingredients?: string[]; portion?: string };
type PlanDay = {
  day: number;
  name: string;
  focus: string;
  meals: { breakfast: Meal; lunch: Meal; dinner: Meal; snack: Meal };
  movement: { type: string; title: string; minutes: number; intensity: string; instructions: string[]; alternative: string };
  habit: string;
  encouragement: string;
};
type Plan = {
  title: string;
  intro: string;
  weeklyFocus: string;
  safetyNote: string;
  waterTip: string;
  sleepTip: string;
  days: PlanDay[];
  strengthGuide: { exercise: string; sets: string; reps: string; how: string; easier: string }[];
  swimGuide: { part: string; minutes: number; how: string }[];
  shoppingList: Record<string, string[]>;
  checkInQuestions: string[];
  medicalReminder: string;
};
type Profile = {
  age: number;
  height: number;
  weight: number;
  targetWeight: number;
  activity: "starter" | "light" | "regular";
  diet: "flex" | "vegetarian" | "pescetarian";
  trainingPlace: "home" | "gym" | "mix";
  pace: "gentle" | "steady";
  minutes: number;
  walk: boolean;
  swim: boolean;
  strength: boolean;
  knees: boolean;
  back: boolean;
  diabetes: boolean;
  heart: boolean;
  pregnant: boolean;
  eatingDisorder: boolean;
  allergies: string;
  dislikes: string;
  cookingMinutes: number;
  consent: boolean;
};
type Checkin = { day: string; item_id: string; completed: number; weight?: number; mood?: number };
type Tab = "today" | "week" | "food" | "training" | "progress";

const initialProfile: Profile = {
  age: 45,
  height: 178,
  weight: 112,
  targetWeight: 100,
  activity: "starter",
  diet: "flex",
  trainingPlace: "home",
  pace: "gentle",
  minutes: 25,
  walk: true,
  swim: true,
  strength: true,
  knees: false,
  back: false,
  diabetes: false,
  heart: false,
  pregnant: false,
  eatingDisorder: false,
  allergies: "",
  dislikes: "",
  cookingMinutes: 30,
  consent: false,
};

async function api(path: string, options: RequestInit = {}, csrf = "") {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(csrf ? { "X-CSRF-Token": csrf } : {}), ...options.headers },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Noget gik galt. Prøv igen.");
  return data;
}

function todayKey() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Copenhagen" }).format(new Date());
}

function Brand() {
  return <span className="brand"><span className="brand-mark">F</span><span><b>FRI FORM</b><small>Et lettere liv, ét skridt ad gangen</small></span></span>;
}

export default function App() {
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const [csrf, setCsrf] = useState("");
  const [profile, setProfile] = useState<Profile>(initialProfile);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [provider, setProvider] = useState("");
  const [checkins, setCheckins] = useState<Checkin[]>([]);
  const [authOpen, setAuthOpen] = useState(false);

  const refresh = async () => {
    try {
      const data = await api("/api/me");
      if (data.authenticated) {
        setUser(data.user);
        setCsrf(data.csrf);
        if (data.profile) setProfile(data.profile);
        if (data.latestPlan) {
          setPlan(data.latestPlan.plan);
          setProvider(data.latestPlan.provider);
        }
        setCheckins(data.checkins || []);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  if (loading) return <div className="loading-screen"><Brand /><span className="loader" /><p>Gør din plan klar…</p></div>;
  if (!user) return <Landing onStart={() => setAuthOpen(true)} authOpen={authOpen} setAuthOpen={setAuthOpen} onAuth={refresh} />;
  if (!plan) return <Onboarding user={user} csrf={csrf} profile={profile} setProfile={setProfile} onPlan={(value, source) => { setPlan(value); setProvider(source); }} onLogout={() => logout(csrf, setUser)} />;
  return <Dashboard user={user} csrf={csrf} plan={plan} provider={provider} profile={profile} checkins={checkins} setCheckins={setCheckins} onNewPlan={() => setPlan(null)} onLogout={() => logout(csrf, setUser)} />;
}

async function logout(csrf: string, setUser: (user: User | null) => void) {
  await api("/api/auth/logout", { method: "POST", body: "{}" }, csrf).catch(() => null);
  setUser(null);
}

function Landing({ onStart, authOpen, setAuthOpen, onAuth }: { onStart: () => void; authOpen: boolean; setAuthOpen: (v: boolean) => void; onAuth: () => Promise<void> }) {
  return <main>
    <header className="public-header"><Brand /><nav><a href="#saadan">Sådan virker det</a><a href="#indhold">Din plan</a><button className="link-button" onClick={() => setAuthOpen(true)}>Log ind</button><button className="primary small" onClick={onStart}>Start gratis</button></nav></header>
    <section className="hero">
      <div className="hero-copy"><p className="eyebrow">100 % GRATIS · INGEN BETALINGSMUR</p><h1>En personlig plan,<br /><em>der passer til dit liv.</em></h1><p className="lead">Få en grundig ugeplan med almindelig mad, gåture, svømning og styrketræning. Din plan husker din fremgang og møder dig igen i morgen.</p><div className="hero-actions"><button className="primary large" onClick={onStart}>Lav min gratis plan <span>→</span></button><span>Ca. 5 minutter<br />Planen sendes også på mail</span></div><div className="trust-row"><span>✓ Altid gratis</span><span>✓ Dansk AI-plan</span><span>✓ Gemmes sikkert</span></div></div>
      <div className="phone-card"><div className="phone-top"><span>I DAG</span><span className="streak">3 dage i gang</span></div><h2>Godmorgen 👋</h2><p>Kun tre overskuelige ting i dag.</p><PreviewTask done icon="✓" title="Morgenmad der mætter" meta="Havregrød, skyr og bær" /><PreviewTask icon="↗" title="25 minutters gåtur" meta="Roligt snakketempo" /><PreviewTask icon="½" title="Tallerkenmodellen" meta="Grønt på halvdelen" /><div className="coach-note"><b>Din plan må gerne bøje.</b><span>En mindre dag er stadig en dag i den rigtige retning.</span></div></div>
    </section>
    <section className="metric-strip"><div><b>7</b><span>detaljerede dage</span></div><div><b>4</b><span>daglige måltidsforslag</span></div><div><b>3</b><span>måder at bevæge sig</span></div><div><b>0 kr.</b><span>nu og fremover</span></div></section>
    <section id="saadan" className="steps-section"><p className="eyebrow">EN PLAN, IKKE ENDNU EN KUR</p><h2>Vi gør det grundigt.<br />Men aldrig uoverskueligt.</h2><div className="three-grid"><Feature n="01" title="Fortæl om din hverdag" text="Vælg madpræferencer, tid, udgangspunkt og de motionsformer, du faktisk kan se dig selv lave." /><Feature n="02" title="AI bygger din uge" text="En klog model samler kost, gåture, svømning og styrke i én sammenhængende dansk plan." /><Feature n="03" title="Følg ét døgn ad gangen" text="Sæt flueben, se din uge og få planen på mail. Du kan altid justere og begynde igen." /></div></section>
    <section id="indhold" className="plan-showcase"><div><p className="eyebrow">BYGGET TIL VIRKELIGHEDEN</p><h2>Alle dele af din uge<br />samlet ét sted.</h2><p>Hver dag indeholder konkrete måltider, portionsgreb, bevægelse med alternativer og en lille vane. Ugen samles med indkøbsliste, styrkeguide og svømmeprogram.</p><button className="primary" onClick={onStart}>Opret gratis konto</button></div><div className="showcase-list"><span><i>🥣</i><b>Mad</b><small>Ingredienser, portioner og alternativer</small></span><span><i>🚶</i><b>Gåture</b><small>Tid, tempo og kortere mulighed</small></span><span><i>🏊</i><b>Svømning</b><small>Opvarmning, intervaller og rolig afslutning</small></span><span><i>💪</i><b>Styrke</b><small>Øvelser, gentagelser og lettere varianter</small></span></div></section>
    <section className="closing"><p>Det første mål er ikke hele rejsen.</p><h2>Det er at gøre i morgen<br />lidt lettere end i dag.</h2><button className="primary light large" onClick={onStart}>Start min gratis plan →</button></section>
    <PublicFooter />
    {authOpen && <AuthModal onClose={() => setAuthOpen(false)} onAuth={onAuth} />}
  </main>;
}

function PreviewTask({ done, icon, title, meta }: { done?: boolean; icon: string; title: string; meta: string }) {
  return <div className={`preview-task ${done ? "done" : ""}`}><i>{icon}</i><span><b>{title}</b><small>{meta}</small></span><button aria-label="Markér opgave">{done ? "✓" : ""}</button></div>;
}

function Feature({ n, title, text }: { n: string; title: string; text: string }) {
  return <article className="feature"><span>{n}</span><div className={`feature-art art-${n}`}><i /><b /><em /></div><h3>{title}</h3><p>{text}</p></article>;
}

function AuthModal({ onClose, onAuth }: { onClose: () => void; onAuth: () => Promise<void> }) {
  const [mode, setMode] = useState<"register" | "login">("register");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setError(""); setBusy(true);
    const form = new FormData(event.currentTarget);
    try {
      await api(`/api/auth/${mode}`, { method: "POST", body: JSON.stringify({ name: form.get("name"), email: form.get("email"), password: form.get("password") }) });
      await onAuth(); onClose();
    } catch (err) { setError(err instanceof Error ? err.message : "Noget gik galt."); } finally { setBusy(false); }
  };
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><section className="auth-modal" role="dialog" aria-modal="true" aria-labelledby="auth-title"><button className="modal-close" onClick={onClose} aria-label="Luk">×</button><Brand /><p className="eyebrow">{mode === "register" ? "DIN GRATIS KONTO" : "VELKOMMEN TILBAGE"}</p><h2 id="auth-title">{mode === "register" ? "Gem din plan og fortsæt i morgen." : "Log ind på din plan."}</h2><p>{mode === "register" ? "Ingen prøveperiode. Intet betalingskort. Bare din personlige plan." : "Din plan, dine flueben og din fremgang venter på dig."}</p><form onSubmit={submit}>{mode === "register" && <label>Fornavn<input name="name" autoComplete="name" required minLength={2} placeholder="Dit navn" /></label>}<label>E-mail<input name="email" type="email" autoComplete="email" required placeholder="dig@eksempel.dk" /></label><label>Adgangskode<input name="password" type="password" autoComplete={mode === "register" ? "new-password" : "current-password"} required minLength={10} placeholder="Mindst 10 tegn" /></label>{error && <p className="form-error" role="alert">{error}</p>}<button className="primary full" disabled={busy}>{busy ? "Et øjeblik…" : mode === "register" ? "Opret gratis konto" : "Log ind"}</button></form><button className="switch-auth" onClick={() => { setMode(mode === "register" ? "login" : "register"); setError(""); }}>{mode === "register" ? "Har du allerede en konto? Log ind" : "Ny her? Opret gratis konto"}</button><small>Ved at oprette en konto accepterer du, at dine oplysninger gemmes sikkert for at levere tjenesten. Du kan altid slette kontoen.</small></section></div>;
}

function Onboarding({ user, csrf, profile, setProfile, onPlan, onLogout }: { user: User; csrf: string; profile: Profile; setProfile: (p: Profile) => void; onPlan: (p: Plan, provider: string) => void; onLogout: () => void }) {
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const update = <K extends keyof Profile>(key: K, value: Profile[K]) => setProfile({ ...profile, [key]: value });
  const generate = async () => {
    setError(""); setBusy(true);
    try {
      const data = await api("/api/plan/generate", { method: "POST", body: JSON.stringify({ profile }) }, csrf);
      onPlan(data.plan, data.provider);
      if (data.email_error) sessionStorage.setItem("friform-email-warning", data.email_error);
    } catch (err) { setError(err instanceof Error ? err.message : "Planen kunne ikke laves."); setBusy(false); }
  };
  const titles = ["Dit udgangspunkt", "Mad der passer til dig", "Bevægelse på din måde", "Helbred og samtykke"];
  return <main className="onboarding"><header className="app-header"><Brand /><div><span>Hej, {user.name}</span><button className="link-button" onClick={onLogout}>Log ud</button></div></header><div className="onboard-shell"><aside><p className="eyebrow">DIN PROFIL</p><h1>En god plan starter med at forstå din hverdag.</h1><p>Der er ingen rigtige svar. Vælg det, der ligner en normal uge.</p><ol>{titles.map((title, index) => <li className={index === step ? "active" : index < step ? "done" : ""} key={title}><i>{index < step ? "✓" : index + 1}</i><span>{title}</span></li>)}</ol></aside><section className="onboard-card"><div className="onboard-progress"><span>Trin {step + 1} af 4</span><i><b style={{ width: `${(step + 1) * 25}%` }} /></i></div>{step === 0 && <><p className="eyebrow">LAD OS STARTE ROLIGT</p><h2>Hvor begynder du?</h2><p className="sub">Cirka-tal er helt fine. Planen bruger dem til at vælge et realistisk tempo.</p><div className="field-grid"><NumberField label="Alder" value={profile.age} min={18} max={80} unit="år" onChange={(v) => update("age", v)} /><NumberField label="Højde" value={profile.height} min={130} max={220} unit="cm" onChange={(v) => update("height", v)} /><NumberField label="Vægt nu" value={profile.weight} min={40} max={300} unit="kg" onChange={(v) => update("weight", v)} /><NumberField label="Første målvægt" value={profile.targetWeight} min={40} max={280} unit="kg" onChange={(v) => update("targetWeight", v)} /></div><Choice label="Dit aktivitetsniveau" value={profile.activity} onChange={(v) => update("activity", v as Profile["activity"])} options={[['starter','Jeg starter næsten fra nul'],['light','Jeg bevæger mig lidt'],['regular','Jeg er allerede regelmæssigt aktiv']]} /><Choice label="Tempo for planen" value={profile.pace} onChange={(v) => update("pace", v as Profile["pace"])} options={[['gentle','Blid start'],['steady','Rolig, men stabil fremgang']]} /></>}
        {step === 1 && <><p className="eyebrow">ALMINDELIG MAD</p><h2>Hvordan vil du helst spise?</h2><p className="sub">Ingen forbudslister. Vi tilpasser råvarer, portioner og tidsforbrug.</p><Choice label="Kostretning" value={profile.diet} onChange={(v) => update("diet", v as Profile["diet"])} options={[['flex','Fleksibelt – kød, fisk og grønt'],['vegetarian','Vegetarisk'],['pescetarian','Vegetarisk + fisk']]} /><div className="field-grid"><NumberField label="Tid til aftensmad" value={profile.cookingMinutes} min={10} max={90} unit="min" onChange={(v) => update("cookingMinutes", v)} /><label className="text-field">Allergier eller intolerancer<input value={profile.allergies} onChange={(e) => update("allergies", e.target.value)} placeholder="Fx nødder eller laktose" /></label><label className="text-field wide">Mad du ikke bryder dig om<input value={profile.dislikes} onChange={(e) => update("dislikes", e.target.value)} placeholder="Fx fisk, svampe eller stærk mad" /></label></div></>}
        {step === 2 && <><p className="eyebrow">VÆLG DET MULIGE</p><h2>Hvordan vil du bevæge dig?</h2><p className="sub">Vælg gerne flere. Hver aktivitet får et kortere alternativ til travle eller trætte dage.</p><div className="activity-select"><Toggle icon="🚶" title="Gåture" text="Roligt tempo, korte eller længere ture" checked={profile.walk} onChange={(v) => update("walk", v)} /><Toggle icon="🏊" title="Svømning" text="Baner, gang i vand og pauser" checked={profile.swim} onChange={(v) => update("swim", v)} /><Toggle icon="💪" title="Styrke" text="Hjemme eller i træningscenter" checked={profile.strength} onChange={(v) => update("strength", v)} /></div><div className="field-grid"><NumberField label="Tid pr. træningsdag" value={profile.minutes} min={10} max={90} unit="min" onChange={(v) => update("minutes", v)} /></div><Choice label="Hvor træner du helst?" value={profile.trainingPlace} onChange={(v) => update("trainingPlace", v as Profile["trainingPlace"])} options={[['home','Hjemme'],['gym','Træningscenter'],['mix','En blanding']]} /><div className="considerations"><p>Skal planen tage hensyn?</p><label><input type="checkbox" checked={profile.knees} onChange={(e) => update("knees", e.target.checked)} /> Knæ</label><label><input type="checkbox" checked={profile.back} onChange={(e) => update("back", e.target.checked)} /> Ryg</label></div></>}
        {step === 3 && <><p className="eyebrow">SIKKERHED FØRST</p><h2>Er der noget vigtigt, planen skal vide?</h2><p className="sub">Svarene bruges til at stoppe eller gøre planen mere forsigtig. Fri Form erstatter ikke læge eller diætist.</p><div className="health-list"><label><input type="checkbox" checked={profile.diabetes} onChange={(e) => update("diabetes", e.target.checked)} /><span><b>Diabetes eller blodsukkerbehandling</b><small>Tal med din behandler ved ændringer i kost og aktivitet.</small></span></label><label><input type="checkbox" checked={profile.heart} onChange={(e) => update("heart", e.target.checked)} /><span><b>Hjertesygdom</b><small>Vi stopper automatisk planlægningen og henviser til læge.</small></span></label><label><input type="checkbox" checked={profile.pregnant} onChange={(e) => update("pregnant", e.target.checked)} /><span><b>Gravid</b><small>Vægttab bør planlægges med jordemoder eller læge.</small></span></label><label><input type="checkbox" checked={profile.eatingDisorder} onChange={(e) => update("eatingDisorder", e.target.checked)} /><span><b>Nuværende eller tidligere spiseforstyrrelse</b><small>En individuel plan bør laves med en fagperson.</small></span></label></div><label className="consent"><input type="checkbox" checked={profile.consent} onChange={(e) => update("consent", e.target.checked)} /><span><b>Jeg accepterer behandlingen af mine oplysninger</b><small>Din profil gemmes på Fri Forms server. En pseudonymiseret profil uden navn og e-mail sendes til OpenCode Go for at skrive planen. Du kan slette alt fra din konto.</small></span></label>{error && <p className="form-error" role="alert">{error}</p>}{busy && <div className="generating"><span className="loader" /><div><b>Din uge bliver skrevet…</b><small>AI’en samler mad, aktiviteter og alternativer. Det tager normalt 30–120 sekunder.</small></div></div>}</>}
        <div className="onboard-actions"><button className="secondary" onClick={() => step > 0 ? setStep(step - 1) : onLogout()}>{step > 0 ? "← Tilbage" : "Log ud"}</button><button className="primary" disabled={busy || (step === 3 && !profile.consent)} onClick={() => step < 3 ? setStep(step + 1) : generate()}>{step < 3 ? "Fortsæt →" : busy ? "Laver planen…" : "Lav og send min plan →"}</button></div></section></div></main>;
}

function NumberField({ label, value, min, max, unit, onChange }: { label: string; value: number; min: number; max: number; unit: string; onChange: (v: number) => void }) {
  return <label className="number-field"><span>{label}</span><div><input type="number" value={value} min={min} max={max} onChange={(e) => onChange(Number(e.target.value))} /><b>{unit}</b></div></label>;
}

function Choice({ label, value, options, onChange }: { label: string; value: string; options: string[][]; onChange: (v: string) => void }) {
  return <fieldset className="choice"><legend>{label}</legend><div>{options.map(([key, text]) => <label key={key} className={value === key ? "selected" : ""}><input type="radio" checked={value === key} onChange={() => onChange(key)} /><span>{text}</span></label>)}</div></fieldset>;
}

function Toggle({ icon, title, text, checked, onChange }: { icon: string; title: string; text: string; checked: boolean; onChange: (v: boolean) => void }) {
  return <label className={checked ? "selected" : ""}><input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} /><i>{icon}</i><span><b>{title}</b><small>{text}</small></span><em>{checked ? "✓" : "+"}</em></label>;
}

function Dashboard({ user, csrf, plan, provider, profile, checkins, setCheckins, onNewPlan, onLogout }: { user: User; csrf: string; plan: Plan; provider: string; profile: Profile; checkins: Checkin[]; setCheckins: (c: Checkin[]) => void; onNewPlan: () => void; onLogout: () => void }) {
  const [tab, setTab] = useState<Tab>("today");
  const [notice, setNotice] = useState(sessionStorage.getItem("friform-email-warning") || "");
  const [emailBusy, setEmailBusy] = useState(false);
  const index = (new Date().getDay() + 6) % 7;
  const day = plan.days[index] || plan.days[0];
  const key = todayKey();
  const completed = new Set(checkins.filter((c) => c.day === key && c.completed).map((c) => c.item_id));
  const toggle = async (itemId: string) => {
    const isDone = completed.has(itemId);
    const next = checkins.filter((c) => !(c.day === key && c.item_id === itemId));
    next.push({ day: key, item_id: itemId, completed: isDone ? 0 : 1 });
    setCheckins(next);
    try { await api("/api/checkin", { method: "POST", body: JSON.stringify({ day: key, itemId, completed: !isDone }) }, csrf); }
    catch { setNotice("Fluebenet kunne ikke gemmes. Prøv igen."); }
  };
  const resend = async () => {
    setEmailBusy(true); setNotice("");
    try { await api("/api/plan/email", { method: "POST", body: "{}" }, csrf); setNotice(`Planen er sendt til ${user.email}.`); sessionStorage.removeItem("friform-email-warning"); }
    catch (err) { setNotice(err instanceof Error ? err.message : "Mailen kunne ikke sendes."); } finally { setEmailBusy(false); }
  };
  const nav: [Tab, string, string][] = [["today","I dag","☀"],["week","Ugen","▦"],["food","Mad","◒"],["training","Træning","↗"],["progress","Fremgang","◎"]];
  return <main className="app"><header className="app-header"><Brand /><div className="user-menu"><span><b>{user.name}</b><small>{user.email}</small></span><button className="link-button" onClick={onLogout}>Log ud</button></div></header><div className="app-layout"><aside className="side-nav"><p className="eyebrow">MIN PLAN</p>{nav.map(([id, label, icon]) => <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}><i>{icon}</i>{label}</button>)}<div className="side-card"><b>Ugens fokus</b><p>{plan.weeklyFocus}</p></div><button className="new-plan" onClick={onNewPlan}>↻ Tilpas eller lav ny plan</button></aside><section className="main-panel">{notice && <div className="notice"><span>{notice}</span><button onClick={() => setNotice("")}>×</button></div>}{tab === "today" && <TodayView day={day} completed={completed} toggle={toggle} onOpen={(next) => setTab(next)} />}{tab === "week" && <WeekView plan={plan} />}{tab === "food" && <FoodView plan={plan} />}{tab === "training" && <TrainingView plan={plan} />}{tab === "progress" && <ProgressView plan={plan} profile={profile} csrf={csrf} checkins={checkins} setCheckins={setCheckins} resend={resend} emailBusy={emailBusy} provider={provider} />}</section></div><nav className="mobile-nav">{nav.map(([id,label,icon]) => <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}><i>{icon}</i><span>{label}</span></button>)}</nav></main>;
}

function TodayView({ day, completed, toggle, onOpen }: { day: PlanDay; completed: Set<string>; toggle: (id: string) => void; onOpen: (t: Tab) => void }) {
  const tasks = [{ id: "breakfast", icon: "🥣", title: day.meals.breakfast.title, text: day.meals.breakfast.portion }, { id: "movement", icon: day.movement.type === "svømning" ? "🏊" : day.movement.type === "styrke" ? "💪" : "🚶", title: day.movement.title, text: `${day.movement.minutes} min · ${day.movement.intensity}` }, { id: "habit", icon: "✦", title: day.habit, text: "Dagens lille vane" }, { id: "dinner", icon: "½", title: day.meals.dinner.title, text: day.meals.dinner.portion }];
  return <><div className="page-heading"><div><p className="eyebrow">{day.name.toUpperCase()} · DAG {day.day}</p><h1>I dag gør vi det<br />muligt at lykkes.</h1><p>{day.focus}</p></div><div className="completion-ring" style={{ "--done": `${completed.size * 25}%` } as React.CSSProperties}><span><b>{Math.min(completed.size, 4)}</b><small>af 4</small></span></div></div><div className="today-layout"><section className="daily-tasks"><div className="section-head"><h2>Dagens plan</h2><span>{Math.min(completed.size, 4)}/4 klaret</span></div>{tasks.map((task) => <button key={task.id} className={completed.has(task.id) ? "done" : ""} onClick={() => toggle(task.id)}><i>{completed.has(task.id) ? "✓" : task.icon}</i><span><b>{task.title}</b><small>{task.text}</small></span><em>{completed.has(task.id) ? "Klaret" : "Markér"}</em></button>)}<blockquote>“{day.encouragement}”</blockquote></section><aside className="today-detail"><div className="movement-card"><p className="eyebrow">DAGENS BEVÆGELSE</p><h2>{day.movement.title}</h2><span className="duration">{day.movement.minutes}<small>minutter</small></span><ol>{day.movement.instructions.map((item) => <li key={item}>{item}</li>)}</ol><p className="alternative"><b>Kortere alternativ:</b> {day.movement.alternative}</p><button onClick={() => onOpen("training")}>Se træningsguiden →</button></div><div className="mini-tips"><span><b>💧 Vand</b><small>Et glas til hvert hovedmåltid</small></span><span><b>🌙 Søvn</b><small>En rolig afslutning tæller</small></span></div></aside></div></>;
}

function WeekView({ plan }: { plan: Plan }) {
  const [open, setOpen] = useState(0);
  return <><div className="page-heading compact"><div><p className="eyebrow">DIN PERSONLIGE UGE</p><h1>{plan.title}</h1><p>{plan.intro}</p></div></div><div className="week-grid">{plan.days.map((day, index) => <article className={open === index ? "open" : ""} key={day.day}><button onClick={() => setOpen(open === index ? -1 : index)}><span><small>DAG {day.day}</small><b>{day.name}</b></span><span className="week-activity"><i>{day.movement.type === "svømning" ? "🏊" : day.movement.type === "styrke" ? "💪" : day.movement.type === "restitution" ? "🌿" : "🚶"}</i><b>{day.movement.title}</b><small>{day.movement.minutes} min</small></span><em>{open === index ? "−" : "+"}</em></button>{open === index && <div className="day-details"><div><h3>Dagens måltider</h3><MealLine label="Morgen" meal={day.meals.breakfast} /><MealLine label="Frokost" meal={day.meals.lunch} /><MealLine label="Aften" meal={day.meals.dinner} /><MealLine label="Hvis sulten" meal={day.meals.snack} /></div><div><h3>Bevægelse</h3><p><b>{day.movement.title}</b><br />{day.movement.intensity}</p><ul>{day.movement.instructions.map((item) => <li key={item}>{item}</li>)}</ul><p><b>Alternativ:</b> {day.movement.alternative}</p></div></div>}</article>)}</div><div className="safety-callout"><i>i</i><p><b>Din krop bestemmer tempoet.</b> {plan.safetyNote}</p></div></>;
}

function MealLine({ label, meal }: { label: string; meal: Meal }) { return <p className="meal-line"><span>{label}</span><b>{meal.title}</b><small>{meal.portion}</small></p>; }

function FoodView({ plan }: { plan: Plan }) {
  const [dayIndex, setDayIndex] = useState(0); const day = plan.days[dayIndex];
  return <><div className="page-heading compact"><div><p className="eyebrow">MAD UDEN FORBUD</p><h1>Din madplan</h1><p>Konkrete forslag og portionsgreb. Byt gerne dage og måltider rundt.</p></div></div><div className="day-pills">{plan.days.map((item, index) => <button className={index === dayIndex ? "active" : ""} onClick={() => setDayIndex(index)} key={item.day}>{item.name.slice(0, 3)}</button>)}</div><div className="food-layout"><section className="meal-cards">{Object.entries(day.meals).map(([key, meal]) => <article key={key}><span>{key === "breakfast" ? "🥣" : key === "lunch" ? "🥪" : key === "dinner" ? "🍲" : "🍎"}</span><div><p>{key === "breakfast" ? "MORGEN" : key === "lunch" ? "FROKOST" : key === "dinner" ? "AFTEN" : "HVIS SULTEN"}</p><h3>{meal.title}</h3>{meal.ingredients && <small>{meal.ingredients.join(" · ")}</small>}<em>{meal.portion}</em></div></article>)}</section><aside><div className="plate-card"><div className="plate"><span>½<small>grønt</small></span><i>¼<small>protein</small></i><b>¼<small>fuldkorn<br />eller kartofler</small></b></div><h3>Tallerkenmodellen</h3><p>Et enkelt pejlemærke uden at veje og tælle alt.</p></div><div className="tips-card"><p>💧 {plan.waterTip}</p><p>🌙 {plan.sleepTip}</p></div></aside></div><Shopping plan={plan} /></>;
}

function Shopping({ plan }: { plan: Plan }) { const labels: Record<string,string> = { "grønt":"Grønt og frugt", "protein":"Protein", "fuldkornOgKartofler":"Fuldkorn og kartofler", "andet":"Det øvrige" }; return <section className="shopping"><div className="section-head"><h2>Ugens indkøbsliste</h2><button onClick={() => window.print()}>Print</button></div><div>{Object.entries(plan.shoppingList).map(([group, items]) => <article key={group}><h3>{labels[group] || group}</h3>{items.map((item) => <label key={item}><input type="checkbox" /> {item}</label>)}</article>)}</div></section>; }

function TrainingView({ plan }: { plan: Plan }) {
  return <><div className="page-heading compact"><div><p className="eyebrow">GÅ · SVØM · BLIV STÆRKERE</p><h1>Din træningsguide</h1><p>Alle pas starter roligt. Du skal kunne kontrollere bevægelsen og stoppe ved smerte.</p></div></div><section className="training-section"><div className="training-title"><span>💪</span><div><p className="eyebrow">STYRKE</p><h2>Rolige øvelser for hele kroppen</h2></div></div><div className="exercise-list">{plan.strengthGuide.map((item, index) => <article key={item.exercise}><i>{index + 1}</i><div><h3>{item.exercise}</h3><p>{item.how}</p><span>{item.sets} sæt · {item.reps} gentagelser</span><small><b>Lettere:</b> {item.easier}</small></div></article>)}</div></section>{plan.swimGuide.length > 0 && <section className="training-section swim-section"><div className="training-title"><span>🏊</span><div><p className="eyebrow">SVØMNING</p><h2>Et roligt pas i vandet</h2></div></div><div className="swim-timeline">{plan.swimGuide.map((item) => <article key={item.part}><b>{item.minutes}<small>min</small></b><div><h3>{item.part}</h3><p>{item.how}</p></div></article>)}</div></section>}<section className="walk-guide"><span>🚶</span><div><p className="eyebrow">GÅTURE</p><h2>Brug snakketesten</h2><p>Du skal kunne sige en hel sætning uden at hive efter vejret. Er dagen tung, så halver tiden eller del turen i to.</p></div></section></>;
}

function ProgressView({ plan, profile, csrf, checkins, setCheckins, resend, emailBusy, provider }: { plan: Plan; profile: Profile; csrf: string; checkins: Checkin[]; setCheckins: (v: Checkin[]) => void; resend: () => void; emailBusy: boolean; provider: string }) {
  const [weight, setWeight] = useState(profile.weight); const [mood, setMood] = useState(3); const [saved, setSaved] = useState(false); const key = todayKey();
  const completed = checkins.filter((c) => c.completed).length; const days = new Set(checkins.filter((c) => c.completed).map((c) => c.day)).size;
  const save = async () => { await api("/api/checkin", { method: "POST", body: JSON.stringify({ day: key, itemId: "daily-checkin", completed: true, weight, mood }) }, csrf); const next = checkins.filter((c) => !(c.day === key && c.item_id === "daily-checkin")); next.push({ day: key, item_id: "daily-checkin", completed: 1, weight, mood }); setCheckins(next); setSaved(true); };
  const deleteAccount = async () => { if (!window.confirm("Slet konto, profil, planer og alle check-ins permanent?")) return; await api("/api/account", { method: "DELETE" }, csrf); window.location.reload(); };
  return <><div className="page-heading compact"><div><p className="eyebrow">FREMGANG UDEN PRES</p><h1>Se retningen.<br />Ikke kun tallet.</h1><p>Energi, vaner og gentagelser tæller også som fremgang.</p></div></div><div className="stat-grid"><article><span>✓</span><b>{completed}</b><small>små skridt klaret</small></article><article><span>▦</span><b>{days}</b><small>aktive dage</small></article><article><span>↘</span><b>{Math.round((profile.weight - profile.targetWeight) * 10) / 10} kg</b><small>dit første mål</small></article></div><section className="checkin-card"><div><p className="eyebrow">DAGENS CHECK-IN</p><h2>Hvordan går det?</h2><p>Vejning er valgfri. Brug samme tidspunkt og se på udviklingen over flere uger.</p></div><div className="checkin-form"><NumberField label="Vægt i dag" value={weight} min={40} max={300} unit="kg" onChange={setWeight} /><label>Energi i dag<div className="mood-scale">{[1,2,3,4,5].map((n) => <button className={mood === n ? "active" : ""} key={n} onClick={() => setMood(n)}>{n}</button>)}</div></label><button className="primary" onClick={save}>{saved ? "Gemt ✓" : "Gem check-in"}</button></div></section><section className="reflection"><h2>Ugens refleksion</h2>{plan.checkInQuestions.map((question) => <label key={question}>{question}<textarea rows={2} placeholder="Skriv til dig selv…" /></label>)}</section><section className="account-card"><div><p className="eyebrow">DIN KONTO</p><h2>Plan og persondata</h2><p>Planen er lavet med {provider.startsWith("opencode") ? "OpenCode Go" : provider.startsWith("ollama") ? "lokal Gemma" : "den validerede reserveskabelon"}. Navn og e-mail sendes aldrig til AI-modellen.</p></div><div><button className="secondary" onClick={resend} disabled={emailBusy}>{emailBusy ? "Sender…" : "Send hele planen på mail"}</button><button className="danger" onClick={deleteAccount}>Slet min konto og alle data</button></div></section><div className="safety-callout"><i>i</i><p><b>Generel vejledning.</b> {plan.medicalReminder}</p></div></>;
}

function PublicFooter() { return <footer className="public-footer"><Brand /><div><b>Fagligt udgangspunkt</b><a href="https://foedevarestyrelsen.dk/kost-og-foedevarer/alt-om-mad/de-officielle-kostraad/kostraad-til-dig" target="_blank" rel="noreferrer">De officielle Kostråd</a><a href="https://www.sst.dk/vidensbase/forebyggelse/anbefalinger-om-fysisk-aktivitet" target="_blank" rel="noreferrer">Sundhedsstyrelsens aktivitetsråd</a></div><div><b>Privatliv</b><p>Din konto kan slettes direkte i appen. Profilen sendes uden navn og e-mail til AI.</p></div><small>© 2026 Fri Form · En gratis tjeneste fra Dybbol.com · Ikke lægelig rådgivning.</small></footer>; }
