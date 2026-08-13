import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

type User = {
  name: string;
  email: string;
  isAdmin?: boolean;
  programDays?: number | null;
  programStartedAt?: string | null;
  programEndsAt?: string | null;
};
type Meal = {
  title: string;
  ingredients?: string[];
  portion?: string;
  method?: string[];
  prepMinutes?: number;
};
type PlanDay = {
  day: number;
  name: string;
  focus: string;
  meals: { breakfast: Meal; lunch: Meal; dinner: Meal; snack: Meal };
  movement: {
    type: string;
    title: string;
    minutes: number;
    intensity: string;
    instructions: string[];
    alternative: string;
    workoutId?: string;
  };
  habit: string;
  encouragement: string;
};
type ExerciseGuide = {
  id?: string;
  exercise: string;
  videoKey?: string;
  pattern?: string;
  muscleGroups?: string[];
  equipment?: string;
  sets: string;
  reps: string;
  how: string;
  cues?: string[];
  easier: string;
  harder?: string;
  caution?: string;
};
type Plan = {
  title: string;
  intro: string;
  weeklyFocus: string;
  safetyNote: string;
  waterTip: string;
  sleepTip: string;
  days: PlanDay[];
  strengthGuide: ExerciseGuide[];
  exerciseLibrary?: ExerciseGuide[];
  strengthWorkouts?: {
    id: string;
    title: string;
    exerciseIds: string[];
    rounds: number;
    restSeconds: number;
  }[];
  program?: {
    currentWeek: number;
    totalWeeks: number;
    phase: string;
    phaseText: string;
    progression: string;
  };
  dailyLessons?: { day: number; title: string; text: string }[];
  weeklyTargets?: {
    strengthSessions: number;
    walkMinutes: number;
    swimSessions: number;
    recoveryDays: number;
  };
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
  uncontrolledBloodPressure: boolean;
  recentSurgery: boolean;
  mobility: "independent" | "support" | "limited";
  medication: string;
  painAreas: string;
  allergies: string;
  dislikes: string;
  cookingMinutes: number;
  consent: boolean;
};
type Checkin = {
  day: string;
  item_id: string;
  completed: number;
  weight?: number;
  mood?: number;
};
type Tab = "today" | "week" | "food" | "training" | "coach" | "progress" | "admin";

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
  uncontrolledBloodPressure: false,
  recentSurgery: false,
  mobility: "independent",
  medication: "",
  painAreas: "",
  allergies: "",
  dislikes: "",
  cookingMinutes: 30,
  consent: false,
};

async function api(path: string, options: RequestInit = {}, csrf = "") {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRF-Token": csrf } : {}),
      ...options.headers,
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Noget gik galt. Prøv igen.");
  return data;
}

function todayKey() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Copenhagen",
  }).format(new Date());
}

function Brand() {
  return (
    <span className="brand">
      <span className="brand-mark">F</span>
      <span>
        <b>FRI FORM</b>
        <small>Et lettere liv, ét skridt ad gangen</small>
      </span>
    </span>
  );
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
  const [queuedEmail, setQueuedEmail] = useState(
    () => sessionStorage.getItem("friform-plan-queued") || "",
  );

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
          sessionStorage.removeItem("friform-plan-queued");
          setQueuedEmail("");
        }
        setCheckins(data.checkins || []);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  if (loading)
    return (
      <div className="loading-screen">
        <Brand />
        <span className="loader" />
        <p>Gør din plan klar…</p>
      </div>
    );
  const resetPath = window.location.pathname === "/reset-password";
  if (resetPath)
    return (
      <ResetPasswordPage
        token={new URLSearchParams(window.location.search).get("token") || ""}
      />
    );
  const adminPath = window.location.pathname === "/admin";
  if (!user && adminPath) return <AdminAccess onAuth={refresh} />;
  if (!user)
    return (
      <Landing
        onStart={() => setAuthOpen(true)}
        authOpen={authOpen}
        setAuthOpen={setAuthOpen}
        onAuth={refresh}
      />
    );
  if (adminPath && !user.isAdmin)
    return <AdminDenied onLogout={() => logout(csrf, setUser)} />;
  if (adminPath && user.isAdmin)
    return <AdminPortal user={user} onLogout={() => logout(csrf, setUser)} />;
  if (!plan && queuedEmail)
    return (
      <PlanQueued
        email={queuedEmail}
        onLogout={() => {
          sessionStorage.removeItem("friform-plan-queued");
          setQueuedEmail("");
          logout(csrf, setUser);
        }}
      />
    );
  if (!plan)
    return (
      <Onboarding
        user={user}
        csrf={csrf}
        profile={profile}
        setProfile={setProfile}
        onQueued={(email) => {
          sessionStorage.setItem("friform-plan-queued", email);
          setQueuedEmail(email);
        }}
        onLogout={() => logout(csrf, setUser)}
      />
    );
  return (
    <Dashboard
      user={user}
      csrf={csrf}
      plan={plan}
      provider={provider}
      profile={profile}
      checkins={checkins}
      setCheckins={setCheckins}
      setPlan={setPlan}
      setProfile={setProfile}
      onQueued={(email) => {
        sessionStorage.setItem("friform-plan-queued", email);
        setQueuedEmail(email);
        setPlan(null);
      }}
      onLogout={() => logout(csrf, setUser)}
    />
  );
}

async function logout(csrf: string, setUser: (user: User | null) => void) {
  await api("/api/auth/logout", { method: "POST", body: "{}" }, csrf).catch(
    () => null,
  );
  setUser(null);
}

function Landing({
  onStart,
  authOpen,
  setAuthOpen,
  onAuth,
}: {
  onStart: () => void;
  authOpen: boolean;
  setAuthOpen: (v: boolean) => void;
  onAuth: () => Promise<void>;
}) {
  return (
    <main>
      <header className="public-header">
        <Brand />
        <nav>
          <a href="#saadan">Sådan virker det</a>
          <a href="#indhold">Din plan</a>
          <button className="link-button" onClick={() => setAuthOpen(true)}>
            Log ind
          </button>
          <button className="primary small" onClick={onStart}>
            Start gratis
          </button>
        </nav>
      </header>
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">100 % GRATIS · INGEN BETALINGSMUR</p>
          <h1>
            En personlig plan,
            <br />
            <em>der passer til dit liv.</em>
          </h1>
          <p className="lead">
            Få et personligt forløb uge for uge med almindelig mad, gåture,
            svømning og styrketræning. Planen tilpasser sig din fremgang og
            møder dig igen i morgen.
          </p>
          <div className="hero-actions">
            <button className="primary large" onClick={onStart}>
              Lav min gratis plan <span>→</span>
            </button>
            <span>
              Ca. 5 minutter
              <br />
              Planen sendes også på mail
            </span>
          </div>
          <div className="trust-row">
            <span>✓ Altid gratis</span>
            <span>✓ Dansk AI-plan</span>
            <span>✓ Gemmes sikkert</span>
          </div>
        </div>
        <div className="phone-card">
          <div className="phone-top">
            <span>I DAG</span>
            <span className="streak">3 dage i gang</span>
          </div>
          <h2>Godmorgen 👋</h2>
          <p>Kun tre overskuelige ting i dag.</p>
          <PreviewTask
            done
            icon="✓"
            title="Morgenmad der mætter"
            meta="Havregrød, skyr og bær"
          />
          <PreviewTask
            icon="↗"
            title="25 minutters gåtur"
            meta="Roligt snakketempo"
          />
          <PreviewTask
            icon="½"
            title="Tallerkenmodellen"
            meta="Grønt på halvdelen"
          />
          <div className="coach-note">
            <b>Din plan må gerne bøje.</b>
            <span>En mindre dag er stadig en dag i den rigtige retning.</span>
          </div>
        </div>
      </section>
      <section className="metric-strip">
        <div>
          <b>1–26</b>
          <span>uger i dit forløb</span>
        </div>
        <div>
          <b>20</b>
          <span>forskellige øvelser</span>
        </div>
        <div>
          <b>20</b>
          <span>forskellige videoguider</span>
        </div>
        <div>
          <b>0 kr.</b>
          <span>nu og fremover</span>
        </div>
      </section>
      <section id="saadan" className="steps-section">
        <p className="eyebrow">EN PLAN, IKKE ENDNU EN KUR</p>
        <h2>
          Vi gør det grundigt.
          <br />
          Men aldrig uoverskueligt.
        </h2>
        <div className="three-grid">
          <Feature
            n="01"
            title="Fortæl om din hverdag"
            text="Vælg madpræferencer, tid, udgangspunkt og de motionsformer, du faktisk kan se dig selv lave."
          />
          <Feature
            n="02"
            title="AI bygger dit forløb"
            text="En klog model samler kost, gåture, svømning og styrke i en dansk plan, der udvikler sig uge for uge."
          />
          <Feature
            n="03"
            title="Tilpas efter virkeligheden"
            text="Sæt flueben, lav ugens check-in og få næste tilpassede uge på mail. AI-coachen hjælper, når noget driller."
          />
        </div>
      </section>
      <section id="indhold" className="plan-showcase">
        <div>
          <p className="eyebrow">BYGGET TIL VIRKELIGHEDEN</p>
          <h2>
            Alle dele af din uge
            <br />
            samlet ét sted.
          </h2>
          <p>
            Hver dag indeholder opskrifter, portionsgreb, bevægelse med
            alternativer og en lille vane. Du får indkøbsliste, måltidsbytte,
            videoguider, svømmeprogram, fremgang og en personlig AI-coach.
          </p>
          <button className="primary" onClick={onStart}>
            Opret gratis konto
          </button>
        </div>
        <div className="showcase-list">
          <span>
            <i>🥣</i>
            <b>Mad</b>
            <small>Ingredienser, portioner og alternativer</small>
          </span>
          <span>
            <i>🚶</i>
            <b>Gåture</b>
            <small>Tid, tempo og kortere mulighed</small>
          </span>
          <span>
            <i>🏊</i>
            <b>Svømning</b>
            <small>Opvarmning, intervaller og rolig afslutning</small>
          </span>
          <span>
            <i>💪</i>
            <b>Styrke</b>
            <small>Øvelser, gentagelser og lettere varianter</small>
          </span>
        </div>
      </section>
      <section className="closing">
        <p>Det første mål er ikke hele rejsen.</p>
        <h2>
          Det er at gøre i morgen
          <br />
          lidt lettere end i dag.
        </h2>
        <button className="primary light large" onClick={onStart}>
          Start min gratis plan →
        </button>
      </section>
      <PublicFooter />
      {authOpen && (
        <AuthModal onClose={() => setAuthOpen(false)} onAuth={onAuth} />
      )}
    </main>
  );
}

function PreviewTask({
  done,
  icon,
  title,
  meta,
}: {
  done?: boolean;
  icon: string;
  title: string;
  meta: string;
}) {
  return (
    <div className={`preview-task ${done ? "done" : ""}`}>
      <i>{icon}</i>
      <span>
        <b>{title}</b>
        <small>{meta}</small>
      </span>
      <button aria-label="Markér opgave">{done ? "✓" : ""}</button>
    </div>
  );
}

function Feature({
  n,
  title,
  text,
}: {
  n: string;
  title: string;
  text: string;
}) {
  return (
    <article className="feature">
      <span>{n}</span>
      <div className={`feature-art art-${n}`}>
        <i />
        <b />
        <em />
      </div>
      <h3>{title}</h3>
      <p>{text}</p>
    </article>
  );
}

function AuthModal({
  onClose,
  onAuth,
  initialMode = "register",
  afterAuth,
}: {
  onClose: () => void;
  onAuth: () => Promise<void>;
  initialMode?: "register" | "login";
  afterAuth?: () => void;
}) {
  const [mode, setMode] = useState<"register" | "login">(initialMode);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [forgot, setForgot] = useState(false);
  const [capacity, setCapacity] = useState<{
    limit: number;
    enrolled: number;
    remaining: number;
    full: boolean;
  } | null>(null);
  useEffect(() => {
    if (mode === "register") {
      api("/api/capacity")
        .then(setCapacity)
        .catch(() => setCapacity(null));
    }
  }, [mode]);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    const form = new FormData(event.currentTarget);
    try {
      await api(`/api/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          email: form.get("email"),
          password: form.get("password"),
          programDays: form.get("programDays"),
        }),
      });
      await onAuth();
      (afterAuth || onClose)();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Noget gik galt.");
    } finally {
      setBusy(false);
    }
  };
  if (forgot)
    return (
      <ForgotPasswordModal onClose={onClose} onBack={() => setForgot(false)} />
    );
  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <section
        className="auth-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-title"
      >
        <button className="modal-close" onClick={onClose} aria-label="Luk">
          ×
        </button>
        <Brand />
        <p className="eyebrow">
          {mode === "register" ? "DIN GRATIS KONTO" : "VELKOMMEN TILBAGE"}
        </p>
        <h2 id="auth-title">
          {mode === "register"
            ? "Gem din plan og fortsæt i morgen."
            : "Log ind på din plan."}
        </h2>
        <p>
          {mode === "register"
            ? "Ingen prøveperiode. Intet betalingskort. Bare din personlige plan."
            : "Din plan, dine flueben og din fremgang venter på dig."}
        </p>
        {mode === "register" && capacity && (
          <p className={`capacity-note ${capacity.full ? "full" : ""}`}>
            <b>
              {capacity.full
                ? "Alle 20 testpladser er optaget"
                : `${capacity.remaining} af 20 testpladser tilbage`}
            </b>
            <span>De to oprindelige konti tæller ikke med.</span>
          </p>
        )}
        <form onSubmit={submit}>
          {mode === "register" && (
            <>
              <label>
                Fornavn
                <input
                  name="name"
                  autoComplete="name"
                  required
                  minLength={2}
                  placeholder="Dit navn"
                />
              </label>
              <fieldset className="program-choice">
                <legend>Hvor langt et gratis forløb vil du prøve?</legend>
                {[
                  ["7", "1 uge"],
                  ["30", "1 måned"],
                  ["90", "3 måneder"],
                  ["180", "6 måneder"],
                ].map(([value, label], index) => (
                  <label key={value}>
                    <input
                      type="radio"
                      name="programDays"
                      value={value}
                      defaultChecked={index === 1}
                    />
                    <span>{label}</span>
                  </label>
                ))}
              </fieldset>
            </>
          )}
          <label>
            E-mail
            <input
              name="email"
              type="email"
              autoComplete="email"
              required
              placeholder="dig@eksempel.dk"
            />
          </label>
          <label>
            Adgangskode
            <input
              name="password"
              type="password"
              autoComplete={
                mode === "register" ? "new-password" : "current-password"
              }
              required
              minLength={10}
              placeholder="Mindst 10 tegn"
            />
          </label>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button
            className="primary full"
            disabled={busy || (mode === "register" && capacity?.full)}
          >
            {busy
              ? "Et øjeblik…"
              : mode === "register"
                ? "Opret gratis konto"
                : "Log ind"}
          </button>
        </form>
        {mode === "login" && (
          <button className="forgot-link" onClick={() => setForgot(true)}>
            Glemt adgangskode?
          </button>
        )}
        <button
          className="switch-auth"
          onClick={() => {
            setMode(mode === "register" ? "login" : "register");
            setError("");
          }}
        >
          {mode === "register"
            ? "Har du allerede en konto? Log ind"
            : "Ny her? Opret gratis konto"}
        </button>
        <small>
          Ved at oprette en konto accepterer du, at dine oplysninger gemmes
          sikkert for at levere tjenesten. Du kan altid slette kontoen.
        </small>
      </section>
    </div>
  );
}

function ForgotPasswordModal({
  onClose,
  onBack,
}: {
  onClose: () => void;
  onBack: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      await api("/api/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email: form.get("email") }),
      });
      setSent(true);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Mailen kunne ikke bestilles.",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="modal-backdrop" role="presentation">
      <section
        className="auth-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="forgot-title"
      >
        <button className="modal-close" onClick={onClose} aria-label="Luk">
          ×
        </button>
        <Brand />
        <p className="eyebrow">HJÆLP TIL LOGIN</p>
        <h2 id="forgot-title">
          {sent ? "Se efter en mail fra os." : "Glemt adgangskoden?"}
        </h2>
        {sent ? (
          <>
            <p>
              Hvis adressen findes hos Fri Form, har vi sendt et engangslink.
              Det gælder i 60 minutter.
            </p>
            <div className="success-message">
              Tjek også spam eller uønsket post.
            </div>
            <button className="primary full" onClick={onBack}>
              Tilbage til login
            </button>
          </>
        ) : (
          <>
            <p>
              Indtast mailadressen til din konto, så sender vi et sikkert link
              til en ny adgangskode.
            </p>
            <form onSubmit={submit}>
              <label>
                E-mail
                <input
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  placeholder="dig@eksempel.dk"
                />
              </label>
              {error && (
                <p className="form-error" role="alert">
                  {error}
                </p>
              )}
              <button className="primary full" disabled={busy}>
                {busy ? "Sender…" : "Send nulstillingslink"}
              </button>
            </form>
            <button className="switch-auth" onClick={onBack}>
              ← Tilbage til login
            </button>
          </>
        )}
      </section>
    </div>
  );
}

function ResetPasswordPage({ token }: { token: string }) {
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState(
    token ? "" : "Linket mangler eller er ugyldigt.",
  );
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") || "");
    const repeat = String(form.get("repeat") || "");
    if (password !== repeat) {
      setError("De to adgangskoder er ikke ens.");
      return;
    }
    setBusy(true);
    try {
      await api("/api/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ token, password }),
      });
      setDone(true);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Adgangskoden kunne ikke ændres.",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <main className="reset-page">
      <section className="reset-card">
        <Brand />
        <p className="eyebrow">FRI FORM · SIKKERT LOGIN</p>
        <h1>
          {done ? "Din adgangskode er ændret." : "Vælg en ny adgangskode."}
        </h1>
        {done ? (
          <>
            <p>
              Alle gamle login-sessioner er lukket. Du kan nu logge ind med din
              nye adgangskode.
            </p>
            <button
              className="primary large"
              onClick={() => {
                window.location.href = "/";
              }}
            >
              Gå til login
            </button>
          </>
        ) : (
          <form onSubmit={submit}>
            <label>
              Ny adgangskode
              <input
                name="password"
                type="password"
                autoComplete="new-password"
                minLength={10}
                required
                placeholder="Mindst 10 tegn"
              />
            </label>
            <label>
              Gentag adgangskoden
              <input
                name="repeat"
                type="password"
                autoComplete="new-password"
                minLength={10}
                required
              />
            </label>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <button className="primary full" disabled={busy || !token}>
              {busy ? "Gemmer…" : "Gem ny adgangskode"}
            </button>
          </form>
        )}
        <small>
          Linket kan kun bruges én gang og udløber efter 60 minutter.
        </small>
      </section>
    </main>
  );
}

function AdminAccess({ onAuth }: { onAuth: () => Promise<void> }) {
  return (
    <main className="admin-access">
      <div className="admin-access-bg">
        <Brand />
        <p>Beskyttet administratorområde</p>
      </div>
      <AuthModal
        initialMode="login"
        onClose={() => {
          window.location.href = "/";
        }}
        afterAuth={() => window.location.reload()}
        onAuth={onAuth}
      />
    </main>
  );
}

function AdminDenied({ onLogout }: { onLogout: () => void }) {
  return (
    <main className="admin-denied">
      <Brand />
      <h1>Ingen adgang</h1>
      <p>Denne konto er ikke administrator for Fri Form.</p>
      <button className="primary" onClick={onLogout}>
        Log ud
      </button>
      <a href="/">Gå til Fri Form</a>
    </main>
  );
}

function AdminPortal({ user, onLogout }: { user: User; onLogout: () => void }) {
  return (
    <main className="app admin-portal">
      <header className="app-header">
        <Brand />
        <div className="user-menu">
          <span>
            <b>Administrator</b>
            <small>{user.email}</small>
          </span>
          <a className="link-button" href="/">
            Åbn brugerappen
          </a>
          <button className="link-button" onClick={onLogout}>
            Log ud
          </button>
        </div>
      </header>
      <section className="main-panel">
        <AdminView />
      </section>
    </main>
  );
}

function Onboarding({
  user,
  csrf,
  profile,
  setProfile,
  onQueued,
  onLogout,
}: {
  user: User;
  csrf: string;
  profile: Profile;
  setProfile: (p: Profile) => void;
  onQueued: (email: string) => void;
  onLogout: () => void;
}) {
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const update = <K extends keyof Profile>(key: K, value: Profile[K]) =>
    setProfile({ ...profile, [key]: value });
  const generate = async () => {
    setError("");
    setBusy(true);
    try {
      const data = await api(
        "/api/plan/generate",
        { method: "POST", body: JSON.stringify({ profile }) },
        csrf,
      );
      if (!data.job_id) throw new Error("Planjobbet kunne ikke startes.");
      onQueued(user.email);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Planen kunne ikke laves.");
      setBusy(false);
    }
  };
  const titles = [
    "Dit udgangspunkt",
    "Mad der passer til dig",
    "Bevægelse på din måde",
    "Helbred og samtykke",
  ];
  return (
    <main className="onboarding">
      <header className="app-header">
        <Brand />
        <div>
          <span>Hej, {user.name}</span>
          <button className="link-button" onClick={onLogout}>
            Log ud
          </button>
        </div>
      </header>
      <div className="onboard-shell">
        <aside>
          <p className="eyebrow">DIN PROFIL</p>
          <h1>En god plan starter med at forstå din hverdag.</h1>
          <p>Der er ingen rigtige svar. Vælg det, der ligner en normal uge.</p>
          <ol>
            {titles.map((title, index) => (
              <li
                className={
                  index === step ? "active" : index < step ? "done" : ""
                }
                key={title}
              >
                <i>{index < step ? "✓" : index + 1}</i>
                <span>{title}</span>
              </li>
            ))}
          </ol>
        </aside>
        <section className="onboard-card">
          <div className="onboard-progress">
            <span>Trin {step + 1} af 4</span>
            <i>
              <b style={{ width: `${(step + 1) * 25}%` }} />
            </i>
          </div>
          {step === 0 && (
            <>
              <p className="eyebrow">LAD OS STARTE ROLIGT</p>
              <h2>Hvor begynder du?</h2>
              <p className="sub">
                Cirka-tal er helt fine. Planen bruger dem til at vælge et
                realistisk tempo.
              </p>
              <div className="field-grid">
                <NumberField
                  label="Alder"
                  value={profile.age}
                  min={18}
                  max={80}
                  unit="år"
                  onChange={(v) => update("age", v)}
                />
                <NumberField
                  label="Højde"
                  value={profile.height}
                  min={130}
                  max={220}
                  unit="cm"
                  onChange={(v) => update("height", v)}
                />
                <NumberField
                  label="Vægt nu"
                  value={profile.weight}
                  min={40}
                  max={300}
                  unit="kg"
                  onChange={(v) => update("weight", v)}
                />
                <NumberField
                  label="Første målvægt"
                  value={profile.targetWeight}
                  min={40}
                  max={280}
                  unit="kg"
                  onChange={(v) => update("targetWeight", v)}
                />
              </div>
              <Choice
                label="Dit aktivitetsniveau"
                value={profile.activity}
                onChange={(v) => update("activity", v as Profile["activity"])}
                options={[
                  ["starter", "Jeg starter næsten fra nul"],
                  ["light", "Jeg bevæger mig lidt"],
                  ["regular", "Jeg er allerede regelmæssigt aktiv"],
                ]}
              />
              <Choice
                label="Tempo for planen"
                value={profile.pace}
                onChange={(v) => update("pace", v as Profile["pace"])}
                options={[
                  ["gentle", "Blid start"],
                  ["steady", "Rolig, men stabil fremgang"],
                ]}
              />
            </>
          )}
          {step === 1 && (
            <>
              <p className="eyebrow">ALMINDELIG MAD</p>
              <h2>Hvordan vil du helst spise?</h2>
              <p className="sub">
                Ingen forbudslister. Vi tilpasser råvarer, portioner og
                tidsforbrug.
              </p>
              <Choice
                label="Kostretning"
                value={profile.diet}
                onChange={(v) => update("diet", v as Profile["diet"])}
                options={[
                  ["flex", "Fleksibelt – kød, fisk og grønt"],
                  ["vegetarian", "Vegetarisk"],
                  ["pescetarian", "Vegetarisk + fisk"],
                ]}
              />
              <div className="field-grid">
                <NumberField
                  label="Tid til aftensmad"
                  value={profile.cookingMinutes}
                  min={10}
                  max={90}
                  unit="min"
                  onChange={(v) => update("cookingMinutes", v)}
                />
                <label className="text-field">
                  Allergier eller intolerancer
                  <input
                    value={profile.allergies}
                    onChange={(e) => update("allergies", e.target.value)}
                    placeholder="Fx nødder eller laktose"
                  />
                </label>
                <label className="text-field wide">
                  Mad du ikke bryder dig om
                  <input
                    value={profile.dislikes}
                    onChange={(e) => update("dislikes", e.target.value)}
                    placeholder="Fx fisk, svampe eller stærk mad"
                  />
                </label>
              </div>
            </>
          )}
          {step === 2 && (
            <>
              <p className="eyebrow">VÆLG DET MULIGE</p>
              <h2>Hvordan vil du bevæge dig?</h2>
              <p className="sub">
                Vælg gerne flere. Hver aktivitet får et kortere alternativ til
                travle eller trætte dage.
              </p>
              <div className="activity-select">
                <Toggle
                  icon="🚶"
                  title="Gåture"
                  text="Roligt tempo, korte eller længere ture"
                  checked={profile.walk}
                  onChange={(v) => update("walk", v)}
                />
                <Toggle
                  icon="🏊"
                  title="Svømning"
                  text="Baner, gang i vand og pauser"
                  checked={profile.swim}
                  onChange={(v) => update("swim", v)}
                />
                <Toggle
                  icon="💪"
                  title="Styrke"
                  text="Hjemme eller i træningscenter"
                  checked={profile.strength}
                  onChange={(v) => update("strength", v)}
                />
              </div>
              <div className="field-grid">
                <NumberField
                  label="Tid pr. træningsdag"
                  value={profile.minutes}
                  min={10}
                  max={90}
                  unit="min"
                  onChange={(v) => update("minutes", v)}
                />
              </div>
              <Choice
                label="Hvor træner du helst?"
                value={profile.trainingPlace}
                onChange={(v) =>
                  update("trainingPlace", v as Profile["trainingPlace"])
                }
                options={[
                  ["home", "Hjemme"],
                  ["gym", "Træningscenter"],
                  ["mix", "En blanding"],
                ]}
              />
              <Choice
                label="Hvordan bevæger du dig i hverdagen?"
                value={profile.mobility}
                onChange={(v) => update("mobility", v as Profile["mobility"])}
                options={[
                  ["independent", "Uden støtte"],
                  ["support", "Jeg bruger af og til støtte"],
                  ["limited", "Jeg har tydelige begrænsninger"],
                ]}
              />
              <div className="considerations">
                <p>Skal planen tage hensyn?</p>
                <label>
                  <input
                    type="checkbox"
                    checked={profile.knees}
                    onChange={(e) => update("knees", e.target.checked)}
                  />{" "}
                  Knæ
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={profile.back}
                    onChange={(e) => update("back", e.target.checked)}
                  />{" "}
                  Ryg
                </label>
              </div>
            </>
          )}
          {step === 3 && (
            <>
              <p className="eyebrow">SIKKERHED FØRST</p>
              <h2>Er der noget vigtigt, planen skal vide?</h2>
              <p className="sub">
                Svarene bruges til at stoppe eller gøre planen mere forsigtig.
                Fri Form erstatter ikke læge eller diætist.
              </p>
              <div className="health-list">
                <label>
                  <input
                    type="checkbox"
                    checked={profile.diabetes}
                    onChange={(e) => update("diabetes", e.target.checked)}
                  />
                  <span>
                    <b>Diabetes eller blodsukkerbehandling</b>
                    <small>
                      Tal med din behandler ved ændringer i kost og aktivitet.
                    </small>
                  </span>
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={profile.heart}
                    onChange={(e) => update("heart", e.target.checked)}
                  />
                  <span>
                    <b>Hjertesygdom</b>
                    <small>
                      Vi stopper automatisk planlægningen og henviser til læge.
                    </small>
                  </span>
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={profile.pregnant}
                    onChange={(e) => update("pregnant", e.target.checked)}
                  />
                  <span>
                    <b>Gravid</b>
                    <small>
                      Vægttab bør planlægges med jordemoder eller læge.
                    </small>
                  </span>
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={profile.eatingDisorder}
                    onChange={(e) => update("eatingDisorder", e.target.checked)}
                  />
                  <span>
                    <b>Nuværende eller tidligere spiseforstyrrelse</b>
                    <small>
                      En individuel plan bør laves med en fagperson.
                    </small>
                  </span>
                </label>
                <label>
                  <input type="checkbox" checked={profile.uncontrolledBloodPressure} onChange={(e) => update("uncontrolledBloodPressure", e.target.checked)} />
                  <span><b>Uafklaret eller meget højt blodtryk</b><small>Vi stopper planlægningen, indtil det er afklaret med læge.</small></span>
                </label>
                <label>
                  <input type="checkbox" checked={profile.recentSurgery} onChange={(e) => update("recentSurgery", e.target.checked)} />
                  <span><b>Nylig operation eller genoptræningsforløb</b><small>Aktivitet skal først afstemmes med den fagperson, der følger dig.</small></span>
                </label>
              </div>
              <div className="field-grid health-notes">
                <label className="text-field"><span>Medicin, der kan påvirke kost eller aktivitet</span><input value={profile.medication} onChange={(e) => update("medication", e.target.value)} placeholder="Valgfrit – skriv ikke doser eller CPR" /></label>
                <label className="text-field"><span>Andre smerter eller bevægelseshensyn</span><input value={profile.painAreas} onChange={(e) => update("painAreas", e.target.value)} placeholder="Fx skulder eller hofte" /></label>
              </div>
              <label className="consent">
                <input
                  type="checkbox"
                  checked={profile.consent}
                  onChange={(e) => update("consent", e.target.checked)}
                />
                <span>
                  <b>Jeg accepterer behandlingen af mine oplysninger</b>
                  <small>
                    Din profil gemmes på Fri Forms server. En pseudonymiseret
                    profil uden navn og e-mail sendes til OpenCode Go for at
                    skrive planen. Du kan slette alt fra din konto.
                  </small>
                </span>
              </label>
              {error && (
                <p className="form-error" role="alert">
                  {error}
                </p>
              )}
              {busy && (
                <p className="generating">
                  <span className="loader" />
                  <b>Starter planlægningen…</b>
                </p>
              )}
            </>
          )}
          <div className="onboard-actions">
            <button
              className="secondary"
              onClick={() => (step > 0 ? setStep(step - 1) : onLogout())}
            >
              {step > 0 ? "← Tilbage" : "Log ud"}
            </button>
            <button
              className="primary"
              disabled={busy || (step === 3 && !profile.consent)}
              onClick={() => (step < 3 ? setStep(step + 1) : generate())}
            >
              {step < 3
                ? "Fortsæt →"
                : busy
                  ? "Laver planen…"
                  : "Lav og send min plan →"}
            </button>
          </div>
        </section>
      </div>
    </main>
  );
}

function PlanQueued({
  email,
  onLogout,
}: {
  email: string;
  onLogout: () => void;
}) {
  return (
    <main className="queued-page">
      <section className="queued-card">
        <Brand />
        <div className="queued-icon">✓</div>
        <p className="eyebrow">VI ER I GANG</p>
        <h1>Du kan roligt lukke vinduet.</h1>
        <p className="queued-lead">
          Din personlige plan bliver nu lavet som et baggrundsjob. Du behøver
          ikke vente her eller holde siden åben.
        </p>
        <div className="queued-mail">
          <span>Planen sendes til</span>
          <b>{email}</b>
        </div>
        <h2>Når mailen er kommet, kan du logge ind.</h2>
        <p>
          Mailen indeholder et link til din færdige plan. Det tager normalt et
          par minutter. Kig eventuelt i spam, hvis du ikke kan se den.
        </p>
        <button className="primary large" onClick={onLogout}>
          Log ud og gå til forsiden
        </button>
        <small>
          Du må også bare lukke denne fane — arbejdet fortsætter på serveren.
        </small>
      </section>
    </main>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  unit,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  unit: string;
  onChange: (v: number) => void;
}) {
  return (
    <label className="number-field">
      <span>{label}</span>
      <div>
        <input
          type="number"
          value={value}
          min={min}
          max={max}
          onChange={(e) => onChange(Number(e.target.value))}
        />
        <b>{unit}</b>
      </div>
    </label>
  );
}

function Choice({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[][];
  onChange: (v: string) => void;
}) {
  return (
    <fieldset className="choice">
      <legend>{label}</legend>
      <div>
        {options.map(([key, text]) => (
          <label key={key} className={value === key ? "selected" : ""}>
            <input
              type="radio"
              checked={value === key}
              onChange={() => onChange(key)}
            />
            <span>{text}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function Toggle({
  icon,
  title,
  text,
  checked,
  onChange,
}: {
  icon: string;
  title: string;
  text: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className={checked ? "selected" : ""}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <i>{icon}</i>
      <span>
        <b>{title}</b>
        <small>{text}</small>
      </span>
      <em>{checked ? "✓" : "+"}</em>
    </label>
  );
}

function Dashboard({
  user,
  csrf,
  plan,
  provider,
  profile,
  checkins,
  setCheckins,
  setPlan,
  setProfile,
  onQueued,
  onLogout,
}: {
  user: User;
  csrf: string;
  plan: Plan;
  provider: string;
  profile: Profile;
  checkins: Checkin[];
  setCheckins: (c: Checkin[]) => void;
  setPlan: (plan: Plan | null) => void;
  setProfile: (profile: Profile) => void;
  onQueued: (email: string) => void;
  onLogout: () => void;
}) {
  const [tab, setTab] = useState<Tab>("today");
  const [notice, setNotice] = useState(
    sessionStorage.getItem("friform-email-warning") || "",
  );
  const [emailBusy, setEmailBusy] = useState(false);
  const [updateOpen, setUpdateOpen] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const index = (new Date().getDay() + 6) % 7;
  const day = plan.days[index] || plan.days[0];
  const key = todayKey();
  const completed = new Set(
    checkins.filter((c) => c.day === key && c.completed).map((c) => c.item_id),
  );
  const toggle = async (itemId: string) => {
    const isDone = completed.has(itemId);
    const next = checkins.filter(
      (c) => !(c.day === key && c.item_id === itemId),
    );
    next.push({ day: key, item_id: itemId, completed: isDone ? 0 : 1 });
    setCheckins(next);
    try {
      await api(
        "/api/checkin",
        {
          method: "POST",
          body: JSON.stringify({ day: key, itemId, completed: !isDone }),
        },
        csrf,
      );
    } catch {
      setNotice("Fluebenet kunne ikke gemmes. Prøv igen.");
    }
  };
  const resend = async () => {
    setEmailBusy(true);
    setNotice("");
    try {
      await api("/api/plan/email", { method: "POST", body: "{}" }, csrf);
      setNotice(`Planen er sendt til ${user.email}.`);
      sessionStorage.removeItem("friform-email-warning");
    } catch (err) {
      setNotice(
        err instanceof Error ? err.message : "Mailen kunne ikke sendes.",
      );
    } finally {
      setEmailBusy(false);
    }
  };
  const nav: [Tab, string, string][] = [
    ["today", "I dag", "☀"],
    ["week", "Ugen", "▦"],
    ["food", "Mad", "◒"],
    ["training", "Træning", "↗"],
    ["coach", "Coach", "✦"],
    ["progress", "Fremgang", "◎"],
  ];
  if (user.isAdmin) nav.push(["admin", "Admin", "⚙"]);
  return (
    <main className="app">
      <header className="app-header">
        <Brand />
        <div className="user-menu">
          <span>
            <b>{user.name}</b>
            <small>
              {user.email}
              {user.programDays ? ` · ${programLabel(user.programDays)}` : ""}
            </small>
          </span>
          <button
            className="secondary header-update"
            onClick={() => setUpdateOpen(true)}
          >
            Opdater oplysninger
          </button>
          <button className="link-button" onClick={onLogout}>
            Log ud
          </button>
        </div>
      </header>
      <div className="app-layout">
        <aside className="side-nav">
          <p className="eyebrow">MIN PLAN</p>
          {nav.map(([id, label, icon]) => (
            <button
              key={id}
              className={tab === id ? "active" : ""}
              onClick={() => setTab(id)}
            >
              <i>{icon}</i>
              {label}
            </button>
          ))}
          <div className="side-card">
            <b>Ugens fokus</b>
            <p>{plan.weeklyFocus}</p>
          </div>
          <button className="new-plan" onClick={() => setUpdateOpen(true)}>
            ↻ Opdater mine oplysninger
          </button>
        </aside>
        <section className="main-panel">
          {notice && (
            <div className="notice">
              <span>{notice}</span>
              <button onClick={() => setNotice("")}>×</button>
            </div>
          )}
          {plan.program && (
            <section className="program-ribbon">
              <div>
                <span>UGE {plan.program.currentWeek} AF {plan.program.totalWeeks}</span>
                <b>{plan.program.phase}</b>
                <small>{plan.program.phaseText}</small>
              </div>
              <i><b style={{ width: `${Math.round((plan.program.currentWeek / plan.program.totalWeeks) * 100)}%` }} /></i>
              {plan.program.currentWeek < plan.program.totalWeeks && (
                <button className="secondary" onClick={() => setReviewOpen(true)}>Afslut ugen og tilpas næste →</button>
              )}
            </section>
          )}
          {tab === "today" && (
            <TodayView
              day={day}
              completed={completed}
              toggle={toggle}
              onOpen={(next) => setTab(next)}
              lesson={plan.dailyLessons?.find((item) => item.day === day.day)}
            />
          )}
          {tab === "week" && <WeekView plan={plan} />}
          {tab === "food" && <FoodView plan={plan} csrf={csrf} setPlan={setPlan} />}
          {tab === "training" && <TrainingView plan={plan} />}
          {tab === "coach" && <CoachView csrf={csrf} />}
          {tab === "progress" && (
            <ProgressView
              plan={plan}
              profile={profile}
              csrf={csrf}
              checkins={checkins}
              setCheckins={setCheckins}
              resend={resend}
              emailBusy={emailBusy}
              provider={provider}
              onNextWeek={() => setReviewOpen(true)}
            />
          )}
          {tab === "admin" && user.isAdmin && <AdminView />}
        </section>
      </div>
      <nav className={`mobile-nav ${user.isAdmin ? "admin-nav" : ""}`}>
        {nav.map(([id, label, icon]) => (
          <button
            key={id}
            className={tab === id ? "active" : ""}
            onClick={() => setTab(id)}
          >
            <i>{icon}</i>
            <span>{label}</span>
          </button>
        ))}
      </nav>
      {updateOpen && (
        <ProfileUpdateModal
          profile={profile}
          csrf={csrf}
          email={user.email}
          onClose={() => setUpdateOpen(false)}
          onQueued={(next) => {
            setProfile(next);
            setUpdateOpen(false);
            onQueued(user.email);
          }}
        />
      )}
      {reviewOpen && plan.program && (
        <NextWeekModal
          csrf={csrf}
          email={user.email}
          profile={profile}
          week={plan.program.currentWeek}
          onClose={() => setReviewOpen(false)}
          onQueued={() => {
            setReviewOpen(false);
            onQueued(user.email);
          }}
        />
      )}
    </main>
  );
}

function programLabel(days: number) {
  return days === 7
    ? "1 uge"
    : days === 30
      ? "1 måned"
      : days === 90
        ? "3 måneder"
        : days === 180
          ? "6 måneder"
          : `${days} dage`;
}

function NextWeekModal({
  csrf,
  email,
  profile,
  week,
  onClose,
  onQueued,
}: {
  csrf: string;
  email: string;
  profile: Profile;
  week: number;
  onClose: () => void;
  onQueued: () => void;
}) {
  const [weight, setWeight] = useState(profile.weight);
  const [energy, setEnergy] = useState(3);
  const [difficulty, setDifficulty] = useState(3);
  const [pain, setPain] = useState(0);
  const [win, setWin] = useState("");
  const [challenge, setChallenge] = useState("");
  const [nextFocus, setNextFocus] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api(
        "/api/program/next-week",
        { method: "POST", body: JSON.stringify({ weight, energy, difficulty, pain, win, challenge, nextFocus }) },
        csrf,
      );
      if (!result.job_id) throw new Error("Næste uge kunne ikke startes.");
      onQueued();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ugechecket kunne ikke gemmes.");
      setBusy(false);
    }
  };
  const Scale = ({ label, value, setValue, from = 1 }: { label: string; value: number; setValue: (value: number) => void; from?: number }) => (
    <label className="review-scale"><b>{label}</b><span>{Array.from({ length: 6 - from }, (_, index) => index + from).map((number) => <button type="button" className={value === number ? "active" : ""} onClick={() => setValue(number)} key={number}>{number}</button>)}</span></label>
  );
  return (
    <div className="modal-backdrop review-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && !busy && onClose()}>
      <section className="weekly-review-modal" role="dialog" aria-modal="true" aria-labelledby="review-title">
        <button className="modal-close" onClick={onClose} disabled={busy} aria-label="Luk">×</button>
        <p className="eyebrow">UGE {week} · ÆRLIGT, IKKE PERFEKT</p>
        <h2 id="review-title">Lad næste uge passe bedre.</h2>
        <p>Din check-in gemmes og bruges til at tilpasse næste uge. Den nye plan fortsætter i baggrunden og sendes til {email}.</p>
        <form onSubmit={submit}>
          <NumberField label="Vægt – valgfri" value={weight} min={40} max={300} unit="kg" onChange={setWeight} />
          <div className="review-scales">
            <Scale label="Energi" value={energy} setValue={setEnergy} />
            <Scale label="Sværhedsgrad" value={difficulty} setValue={setDifficulty} />
            <Scale label="Smerter under/efter aktivitet" value={pain} setValue={setPain} from={0} />
          </div>
          <label className="text-field">Hvad virkede godt?<textarea rows={2} value={win} onChange={(event) => setWin(event.target.value)} placeholder="Fx de korte gåture var nemme at få gjort" /></label>
          <label className="text-field">Hvad var svært?<textarea rows={2} value={challenge} onChange={(event) => setChallenge(event.target.value)} placeholder="Fx aftensmaden tog for lang tid" /></label>
          <label className="text-field">Noget du ønsker mere eller mindre af?<textarea rows={2} value={nextFocus} onChange={(event) => setNextFocus(event.target.value)} /></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <div className="update-actions"><button type="button" className="secondary" onClick={onClose} disabled={busy}>Ikke nu</button><button className="primary" disabled={busy || !win.trim() || !challenge.trim()}>{busy ? "Starter næste uge…" : "Gem og lav næste uge →"}</button></div>
        </form>
      </section>
    </div>
  );
}

function ProfileUpdateModal({
  profile,
  csrf,
  email,
  onClose,
  onQueued,
}: {
  profile: Profile;
  csrf: string;
  email: string;
  onClose: () => void;
  onQueued: (profile: Profile) => void;
}) {
  const [draft, setDraft] = useState(profile);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const update = <K extends keyof Profile>(key: K, value: Profile[K]) =>
    setDraft({ ...draft, [key]: value });
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api(
        "/api/plan/generate",
        { method: "POST", body: JSON.stringify({ profile: draft }) },
        csrf,
      );
      if (!result.job_id)
        throw new Error("Den opdaterede plan kunne ikke startes.");
      onQueued(draft);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Oplysningerne kunne ikke opdateres.",
      );
      setBusy(false);
    }
  };
  return (
    <div
      className="modal-backdrop update-backdrop"
      role="presentation"
      onMouseDown={(event) =>
        event.target === event.currentTarget && !busy && onClose()
      }
    >
      <section
        className="profile-update-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="update-title"
      >
        <button
          className="modal-close"
          onClick={onClose}
          aria-label="Luk"
          disabled={busy}
        >
          ×
        </button>
        <Brand />
        <p className="eyebrow">OPDATER DIN RETNING</p>
        <h2 id="update-title">Hvad har ændret sig?</h2>
        <p>
          Ret de oplysninger, der ikke længere passer. Vi laver derefter en
          frisk plan og sender den til {email}.
        </p>
        <form onSubmit={submit}>
          <div className="update-grid">
            <NumberField
              label="Vægt nu"
              value={draft.weight}
              min={40}
              max={300}
              unit="kg"
              onChange={(v) => update("weight", v)}
            />
            <NumberField
              label="Første målvægt"
              value={draft.targetWeight}
              min={40}
              max={280}
              unit="kg"
              onChange={(v) => update("targetWeight", v)}
            />
            <NumberField
              label="Tid pr. træningsdag"
              value={draft.minutes}
              min={10}
              max={90}
              unit="min"
              onChange={(v) => update("minutes", v)}
            />
            <NumberField
              label="Tid til aftensmad"
              value={draft.cookingMinutes}
              min={10}
              max={90}
              unit="min"
              onChange={(v) => update("cookingMinutes", v)}
            />
          </div>
          <Choice
            label="Kostretning"
            value={draft.diet}
            onChange={(v) => update("diet", v as Profile["diet"])}
            options={[
              ["flex", "Fleksibelt"],
              ["vegetarian", "Vegetarisk"],
              ["pescetarian", "Vegetarisk + fisk"],
            ]}
          />
          <div className="update-activities">
            <Toggle
              icon="🚶"
              title="Gåture"
              text="Korte eller længere ture"
              checked={draft.walk}
              onChange={(v) => update("walk", v)}
            />
            <Toggle
              icon="🏊"
              title="Svømning"
              text="Baner og pauser"
              checked={draft.swim}
              onChange={(v) => update("swim", v)}
            />
            <Toggle
              icon="💪"
              title="Styrke"
              text="Hjemme eller center"
              checked={draft.strength}
              onChange={(v) => update("strength", v)}
            />
          </div>
          <Choice
            label="Bevægelse i hverdagen"
            value={draft.mobility || "independent"}
            onChange={(v) => update("mobility", v as Profile["mobility"])}
            options={[["independent", "Uden støtte"], ["support", "Af og til støtte"], ["limited", "Tydelige begrænsninger"]]}
          />
          <div className="update-grid text-update-grid">
            <label className="text-field">
              Allergier
              <input
                value={draft.allergies}
                onChange={(e) => update("allergies", e.target.value)}
              />
            </label>
            <label className="text-field">
              Mad du ikke bryder dig om
              <input
                value={draft.dislikes}
                onChange={(e) => update("dislikes", e.target.value)}
              />
            </label>
            <label className="text-field">
              Smerter eller bevægelseshensyn
              <input value={draft.painAreas || ""} onChange={(e) => update("painAreas", e.target.value)} />
            </label>
          </div>
          <label className="consent compact-consent">
            <input
              type="checkbox"
              checked={draft.consent}
              onChange={(e) => update("consent", e.target.checked)}
            />
            <span>
              <b>
                Jeg accepterer, at den opdaterede profil bruges til en ny
                AI-plan.
              </b>
            </span>
          </label>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <div className="update-actions">
            <button
              type="button"
              className="secondary"
              onClick={onClose}
              disabled={busy}
            >
              Annuller
            </button>
            <button className="primary" disabled={busy || !draft.consent}>
              {busy ? "Starter…" : "Opdater og send ny plan →"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function TodayView({
  day,
  completed,
  toggle,
  onOpen,
  lesson,
}: {
  day: PlanDay;
  completed: Set<string>;
  toggle: (id: string) => void;
  onOpen: (t: Tab) => void;
  lesson?: { day: number; title: string; text: string };
}) {
  const movementKind =
    `${day.movement.type} ${day.movement.title}`.toLowerCase();
  const tasks = [
    {
      id: "breakfast",
      icon: "🥣",
      title: day.meals.breakfast.title,
      text: day.meals.breakfast.portion,
    },
    {
      id: "movement",
      icon: movementKind.includes("svøm")
        ? "🏊"
        : movementKind.includes("styrk")
          ? "💪"
          : "🚶",
      title: day.movement.title,
      text: `${day.movement.minutes} min · ${day.movement.intensity}`,
    },
    { id: "habit", icon: "✦", title: day.habit, text: "Dagens lille vane" },
    {
      id: "dinner",
      icon: "½",
      title: day.meals.dinner.title,
      text: day.meals.dinner.portion,
    },
  ];
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">
            {day.name.toUpperCase()} · DAG {day.day}
          </p>
          <h1>
            I dag gør vi det
            <br />
            muligt at lykkes.
          </h1>
          <p>{day.focus}</p>
        </div>
        <div
          className="completion-ring"
          style={{ "--done": `${completed.size * 25}%` } as React.CSSProperties}
        >
          <span>
            <b>{Math.min(completed.size, 4)}</b>
            <small>af 4</small>
          </span>
        </div>
      </div>
      <div className="today-layout">
        <section className="daily-tasks">
          <div className="section-head">
            <h2>Dagens plan</h2>
            <span>{Math.min(completed.size, 4)}/4 klaret</span>
          </div>
          {tasks.map((task) => (
            <button
              key={task.id}
              className={completed.has(task.id) ? "done" : ""}
              onClick={() => toggle(task.id)}
            >
              <i>{completed.has(task.id) ? "✓" : task.icon}</i>
              <span>
                <b>{task.title}</b>
                <small>{task.text}</small>
              </span>
              <em>{completed.has(task.id) ? "Klaret" : "Markér"}</em>
            </button>
          ))}
          <blockquote>“{day.encouragement}”</blockquote>
        </section>
        <aside className="today-detail">
          <div className="movement-card">
            <p className="eyebrow">DAGENS BEVÆGELSE</p>
            <h2>{day.movement.title}</h2>
            <span className="duration">
              {day.movement.minutes}
              <small>minutter</small>
            </span>
            <ol>
              {day.movement.instructions.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ol>
            <p className="alternative">
              <b>Kortere alternativ:</b> {day.movement.alternative}
            </p>
            <button onClick={() => onOpen("training")}>
              Se træningsguiden →
            </button>
          </div>
          <div className="mini-tips">
            <span>
              <b>💧 Vand</b>
              <small>Et glas til hvert hovedmåltid</small>
            </span>
            <span>
              <b>🌙 Søvn</b>
              <small>En rolig afslutning tæller</small>
            </span>
          </div>
        </aside>
      </div>
      {lesson && (
        <section className="daily-lesson">
          <span>3 MIN</span>
          <div>
            <p className="eyebrow">DAGENS LILLE LÆRING</p>
            <h2>{lesson.title}</h2>
            <p>{lesson.text}</p>
          </div>
        </section>
      )}
    </>
  );
}

function WeekView({ plan }: { plan: Plan }) {
  const [open, setOpen] = useState(0);
  return (
    <>
      <div className="page-heading compact">
        <div>
          <p className="eyebrow">DIN PERSONLIGE UGE</p>
          <h1>{plan.title}</h1>
          <p>{plan.intro}</p>
        </div>
      </div>
      {plan.weeklyTargets && (
        <section className="week-targets">
          <article><span>🚶</span><b>{plan.weeklyTargets.walkMinutes} min</b><small>gåture denne uge</small></article>
          <article><span>💪</span><b>{plan.weeklyTargets.strengthSessions} pas</b><small>styrke for hele kroppen</small></article>
          <article><span>🏊</span><b>{plan.weeklyTargets.swimSessions} pas</b><small>svømning</small></article>
          <article><span>🌿</span><b>{plan.weeklyTargets.recoveryDays} dag</b><small>bevidst restitution</small></article>
        </section>
      )}
      <div className="week-grid">
        {plan.days.map((day, index) => {
          const kind =
            `${day.movement.type} ${day.movement.title}`.toLowerCase();
          return (
            <article className={open === index ? "open" : ""} key={day.day}>
              <button onClick={() => setOpen(open === index ? -1 : index)}>
                <span>
                  <small>DAG {day.day}</small>
                  <b>{day.name}</b>
                </span>
                <span className="week-activity">
                  <i>
                    {kind.includes("svøm")
                      ? "🏊"
                      : kind.includes("styrk")
                        ? "💪"
                        : kind.includes("restitution")
                          ? "🌿"
                          : "🚶"}
                  </i>
                  <b>{day.movement.title}</b>
                  <small>{day.movement.minutes} min</small>
                </span>
                <em>{open === index ? "−" : "+"}</em>
              </button>
              {open === index && (
                <div className="day-details">
                  <div>
                    <h3>Dagens måltider</h3>
                    <MealLine label="Morgen" meal={day.meals.breakfast} />
                    <MealLine label="Frokost" meal={day.meals.lunch} />
                    <MealLine label="Aften" meal={day.meals.dinner} />
                    <MealLine label="Hvis sulten" meal={day.meals.snack} />
                  </div>
                  <div>
                    <h3>Bevægelse</h3>
                    <p>
                      <b>{day.movement.title}</b>
                      <br />
                      {day.movement.intensity}
                    </p>
                    <ul>
                      {day.movement.instructions.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                    <p>
                      <b>Alternativ:</b> {day.movement.alternative}
                    </p>
                  </div>
                </div>
              )}
            </article>
          );
        })}
      </div>
      <div className="safety-callout">
        <i>i</i>
        <p>
          <b>Din krop bestemmer tempoet.</b> {plan.safetyNote}
        </p>
      </div>
      {plan.program && <p className="progression-note"><b>Sådan udvikler planen sig:</b> {plan.program.progression}</p>}
    </>
  );
}

function MealLine({ label, meal }: { label: string; meal: Meal }) {
  return (
    <p className="meal-line">
      <span>{label}</span>
      <b>{meal.title}</b>
      <small>{meal.portion}</small>
    </p>
  );
}

function FoodView({
  plan,
  csrf,
  setPlan,
}: {
  plan: Plan;
  csrf: string;
  setPlan: (plan: Plan) => void;
}) {
  const [dayIndex, setDayIndex] = useState(0);
  const [openMeal, setOpenMeal] = useState("");
  const [swapping, setSwapping] = useState("");
  const [error, setError] = useState("");
  const day = plan.days[dayIndex];
  const swapMeal = async (kind: string) => {
    setSwapping(kind);
    setError("");
    try {
      const result = await api(
        "/api/meal/swap",
        { method: "POST", body: JSON.stringify({ day: day.day, kind }) },
        csrf,
      );
      setPlan(result.plan);
      setOpenMeal(kind);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Måltidet kunne ikke byttes.");
    } finally {
      setSwapping("");
    }
  };
  return (
    <>
      <div className="page-heading compact">
        <div>
          <p className="eyebrow">MAD UDEN FORBUD</p>
          <h1>Din madplan</h1>
          <p>
            Konkrete forslag og portionsgreb. Byt gerne dage og måltider rundt.
          </p>
        </div>
      </div>
      <div className="day-pills">
        {plan.days.map((item, index) => (
          <button
            className={index === dayIndex ? "active" : ""}
            onClick={() => setDayIndex(index)}
            key={item.day}
          >
            {item.name.slice(0, 3)}
          </button>
        ))}
      </div>
      <div className="food-layout">
        <section className="meal-cards">
          {Object.entries(day.meals).map(([key, meal]) => (
            <article className={openMeal === key ? "meal-open" : ""} key={key}>
              <span>
                {key === "breakfast"
                  ? "🥣"
                  : key === "lunch"
                    ? "🥪"
                    : key === "dinner"
                      ? "🍲"
                      : "🍎"}
              </span>
              <div>
                <p>
                  {key === "breakfast"
                    ? "MORGEN"
                    : key === "lunch"
                      ? "FROKOST"
                      : key === "dinner"
                        ? "AFTEN"
                        : "HVIS SULTEN"}
                </p>
                <h3>{meal.title}</h3>
                {meal.ingredients && (
                  <small>{meal.ingredients.join(" · ")}</small>
                )}
                <em>{meal.portion}</em>
                <div className="meal-actions">
                  <button className="link-button" onClick={() => setOpenMeal(openMeal === key ? "" : key)}>
                    {openMeal === key ? "Skjul opskrift" : "Se opskrift"}
                  </button>
                  <button className="link-button swap-meal" disabled={swapping === key} onClick={() => swapMeal(key)}>
                    {swapping === key ? "Finder…" : "Byt måltid ↻"}
                  </button>
                </div>
                {openMeal === key && (
                  <div className="meal-recipe">
                    <b>Sådan gør du {meal.prepMinutes ? `· ca. ${meal.prepMinutes} min` : ""}</b>
                    <ol>{(meal.method || ["Tilbered råvarerne enkelt og brug portionsforslaget som pejlemærke."]).map((step) => <li key={step}>{step}</li>)}</ol>
                  </div>
                )}
              </div>
            </article>
          ))}
          {error && <p className="form-error">{error}</p>}
        </section>
        <aside>
          <div className="plate-card">
            <div className="plate">
              <span>
                ½<small>grønt</small>
              </span>
              <i>
                ¼<small>protein</small>
              </i>
              <b>
                ¼
                <small>
                  fuldkorn
                  <br />
                  eller kartofler
                </small>
              </b>
            </div>
            <h3>Tallerkenmodellen</h3>
            <p>Et enkelt pejlemærke uden at veje og tælle alt.</p>
          </div>
          <div className="tips-card">
            <p>💧 {plan.waterTip}</p>
            <p>🌙 {plan.sleepTip}</p>
          </div>
        </aside>
      </div>
      <Shopping plan={plan} />
    </>
  );
}

function Shopping({ plan }: { plan: Plan }) {
  const labels: Record<string, string> = {
    grønt: "Grønt og frugt",
    protein: "Protein",
    fuldkornOgKartofler: "Fuldkorn og kartofler",
    andet: "Det øvrige",
  };
  return (
    <section className="shopping">
      <div className="section-head">
        <h2>Ugens indkøbsliste</h2>
        <button onClick={() => window.print()}>Print</button>
      </div>
      <div>
        {Object.entries(plan.shoppingList).map(([group, items]) => (
          <article key={group}>
            <h3>{labels[group] || group}</h3>
            {items.map((item) => (
              <label key={item}>
                <input type="checkbox" /> {item}
              </label>
            ))}
          </article>
        ))}
      </div>
    </section>
  );
}

function TrainingView({ plan }: { plan: Plan }) {
  const [workoutId, setWorkoutId] = useState(plan.strengthWorkouts?.[0]?.id || "");
  const selectedWorkout = plan.strengthWorkouts?.find((item) => item.id === workoutId);
  const visibleExercises = selectedWorkout
    ? plan.strengthGuide.filter((item) => item.id && selectedWorkout.exerciseIds.includes(item.id))
    : plan.strengthGuide;
  const completeLibrary = plan.exerciseLibrary?.length
    ? plan.exerciseLibrary
    : plan.strengthGuide;
  return (
    <>
      <div className="page-heading compact">
        <div>
          <p className="eyebrow">GÅ · SVØM · BLIV STÆRKERE</p>
          <h1>Din træningsguide</h1>
          <p>
            Alle pas starter roligt. Du skal kunne kontrollere bevægelsen og
            stoppe ved smerte.
          </p>
        </div>
      </div>
      <section className="training-section">
        <div className="training-title">
          <span>💪</span>
          <div>
            <p className="eyebrow">STYRKE</p>
            <h2>Rolige øvelser for hele kroppen</h2>
          </div>
        </div>
        {plan.strengthWorkouts && plan.strengthWorkouts.length > 0 && (
          <div className="workout-picker">
            {plan.strengthWorkouts.map((workout) => (
              <button className={workout.id === workoutId ? "active" : ""} onClick={() => setWorkoutId(workout.id)} key={workout.id}>
                <span>PAS {workout.id}</span><b>{workout.title}</b><small>{workout.rounds} runder · pause efter behov</small>
              </button>
            ))}
            <button className={workoutId === "all" ? "active" : ""} onClick={() => setWorkoutId("all")}>
              <span>BIBLIOTEK</span><b>Alle {completeLibrary.length} øvelser</b><small>Se lettere og sværere varianter</small>
            </button>
          </div>
        )}
        <div className="exercise-list">
          {(workoutId === "all" ? completeLibrary : visibleExercises).map((item, index) => (
            <article className="exercise-card" key={item.exercise}>
              <i className="exercise-number">{index + 1}</i>
              <ExerciseMedia
                exercise={item.exercise}
                how={item.how}
                easier={item.easier}
                harder={item.harder}
                videoKey={item.videoKey}
              />
              <div className="exercise-copy">
                <h3>{item.exercise}</h3>
                <p>{item.how}</p>
                <span>
                  {item.sets} sæt · {item.reps} gentagelser
                </span>
                <small>
                  <b>Lettere:</b> {item.easier}
                </small>
                {item.harder && <small><b>Sværere:</b> {item.harder}</small>}
                {item.equipment && <small className="equipment"><b>Udstyr:</b> {item.equipment}</small>}
              </div>
            </article>
          ))}
        </div>
      </section>
      {plan.swimGuide.length > 0 && (
        <section className="training-section swim-section">
          <div className="training-title">
            <span>🏊</span>
            <div>
              <p className="eyebrow">SVØMNING</p>
              <h2>Et roligt pas i vandet</h2>
            </div>
          </div>
          <div className="swim-timeline">
            {plan.swimGuide.map((item) => (
              <article key={item.part}>
                <b>
                  {item.minutes}
                  <small>min</small>
                </b>
                <div>
                  <h3>{item.part}</h3>
                  <p>{item.how}</p>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}
      <section className="walk-guide">
        <span>🚶</span>
        <div>
          <p className="eyebrow">GÅTURE</p>
          <h2>Brug snakketesten</h2>
          <p>
            Du skal kunne sige en hel sætning uden at hive efter vejret. Er
            dagen tung, så halver tiden eller del turen i to.
          </p>
        </div>
      </section>
    </>
  );
}

type ExerciseVideo = {
  src: string;
  poster: string;
  title: string;
  credit: string;
  source: string;
};

const exerciseVideos: Record<string, ExerciseVideo> = {
  squat: {
    src: "/exercises/chair-squat.mp4",
    poster: "/exercises/chair-squat.webp",
    title: "Kontrolleret squat med træner",
    credit: "Anna Shvets · Pexels",
    source:
      "https://www.pexels.com/video/trainer-explaining-an-exercise-to-a-woman-4838146/",
  },
  wall: {
    src: "/exercises/wall-pushup.mp4",
    poster: "/exercises/wall-pushup.webp",
    title: "Armbøjning mod væg",
    credit: "Ketut Subiyanto · Pexels",
    source:
      "https://www.pexels.com/video/man-doing-a-wall-push-ups-on-the-outdoors-5034321/",
  },
  plank: {
    src: "/exercises/plank.mp4",
    poster: "/exercises/plank.webp",
    title: "Planke med rolig kropslinje",
    credit: "MART PRODUCTION · Pexels",
    source: "https://www.pexels.com/video/a-woman-doing-a-plank-8836970/",
  },
  band: {
    src: "/exercises/resistance-band.mp4",
    poster: "/exercises/resistance-band.webp",
    title: "Træk med elastik",
    credit: "Pexels",
    source:
      "https://www.pexels.com/video/woman-exercising-using-exercise-band-4393123/",
  },
  chair: {
    src: "/exercises/chair-mobility.mp4",
    poster: "/exercises/chair-mobility.webp",
    title: "Rolig bevægelse på stol",
    credit: "Pressmaster · Pexels",
    source:
      "https://www.pexels.com/video/an-instructor-showing-elderly-some-exercise-steps-while-sitting-down-3196290/",
  },
  bridge: {
    src: "/exercises/glute-bridge.mp4", poster: "/exercises/glute-bridge.webp", title: "Hofteløft", credit: "Polina Tankilevitch · Pexels", source: "https://www.pexels.com/video/woman-doing-glute-bridge-exercise-6525487/",
  },
  step: {
    src: "/exercises/step-up.mp4", poster: "/exercises/step-up.webp", title: "Step-up", credit: "Mikhail Nilov · Pexels", source: "https://www.pexels.com/video/a-woman-doing-a-step-up-and-down-exercise-6739968/",
  },
  calf: {
    src: "/exercises/calf-raise.mp4", poster: "/exercises/calf-raise.webp", title: "Hælløft", credit: "Gaurav Kumar · Pexels", source: "https://www.pexels.com/video/intense-calf-workout-in-gym-setting-32115656/",
  },
  shoulder: {
    src: "/exercises/shoulder-press.mp4", poster: "/exercises/shoulder-press.webp", title: "Skulderpres", credit: "JULLIAN PRODUCTION · Pexels", source: "https://www.pexels.com/video/man-lifting-dumbbells-in-home-gym-36623781/",
  },
  biceps: {
    src: "/exercises/biceps-curl.mp4", poster: "/exercises/biceps-curl.webp", title: "Armbøjning med vægt", credit: "MART PRODUCTION · Pexels", source: "https://www.pexels.com/video/a-woman-doing-bicep-curls-at-home-8837117/",
  },
  "bodyweight-squat": {
    src: "/exercises/bodyweight-squat.mp4", poster: "/exercises/bodyweight-squat.webp", title: "Bred squat", credit: "Ketut Subiyanto · Pexels", source: "https://www.pexels.com/video/woman-doing-squat-exercise-5034577/",
  },
  "incline-pushup": {
    src: "/exercises/incline-pushup.mp4", poster: "/exercises/incline-pushup.webp", title: "Armbøjning mod bord", credit: "Mikhail Nilov · Pexels", source: "https://www.pexels.com/video/a-man-doing-incline-push-ups-6970145/",
  },
  "seated-band-row": {
    src: "/exercises/seated-band-row.mp4", poster: "/exercises/seated-band-row.webp", title: "Siddende træk med elastik", credit: "Kampus Production · Pexels", source: "https://www.pexels.com/video/man-doing-seated-row-exercise-6022753/",
  },
  "side-plank": {
    src: "/exercises/side-plank.mp4", poster: "/exercises/side-plank.webp", title: "Sideplanke", credit: "Kampus Production · Pexels", source: "https://www.pexels.com/video/a-man-doing-a-side-plank-6023266/",
  },
  "reverse-lunge": {
    src: "/exercises/reverse-lunge.mp4", poster: "/exercises/reverse-lunge.webp", title: "Baglæns udfald", credit: "ROMAN ODINTSOV · Pexels", source: "https://www.pexels.com/video/woman-doing-lunges-exercise-8233047/",
  },
  "sit-up": {
    src: "/exercises/sit-up.mp4", poster: "/exercises/sit-up.webp", title: "Kontrolleret mavebøjning", credit: "Jill Burrow · Pexels", source: "https://www.pexels.com/video/woman-doing-sit-ups-8893527/",
  },
  "lateral-leg-raise": {
    src: "/exercises/lateral-leg-raise.mp4", poster: "/exercises/lateral-leg-raise.webp", title: "Sidebenløft", credit: "SHVETS production · Pexels", source: "https://www.pexels.com/video/a-woman-doing-a-lateral-leg-raise-exercise-6974513/",
  },
  "lateral-raise": {
    src: "/exercises/lateral-raise.mp4", poster: "/exercises/lateral-raise.webp", title: "Sideløft med håndvægte", credit: "Tima Miroshnichenko · Pexels", source: "https://www.pexels.com/video/a-man-working-out-using-dumbbell-5319088/",
  },
  "triceps-extension": {
    src: "/exercises/triceps-extension.mp4", poster: "/exercises/triceps-extension.webp", title: "Tricepsstræk over hovedet", credit: "Pavel Danilyuk · Pexels", source: "https://www.pexels.com/video/a-man-working-out-6296281/",
  },
  "jumping-jack": {
    src: "/exercises/jumping-jack.mp4", poster: "/exercises/jumping-jack.webp", title: "Sprællemand", credit: "RDNE Stock project · Pexels", source: "https://www.pexels.com/video/women-doing-jumping-jacks-8402086/",
  },
};

function videoForExercise(exercise: string, videoKey?: string) {
  if (videoKey && exerciseVideos[videoKey]) return exerciseVideos[videoKey];
  const name = exercise.toLowerCase();
  if (name.includes("plank")) return exerciseVideos.plank;
  if (
    name.includes("elastik") ||
    name.includes("row") ||
    name.includes("roning")
  )
    return exerciseVideos.band;
  if (
    name.includes("push") ||
    name.includes("armbøj") ||
    name.includes("mod væg") ||
    name.includes("væg-")
  )
    return exerciseVideos.wall;
  if (
    name.includes("squat") ||
    name.includes("knæbøj") ||
    name.includes("sæt dig") ||
    name.includes("rejs")
  )
    return exerciseVideos.squat;
  if (name.includes("stol") || name.includes("siddende"))
    return exerciseVideos.chair;
  return null;
}

function ExerciseMedia({
  exercise,
  how,
  easier,
  harder,
  videoKey,
}: {
  exercise: string;
  how: string;
  easier: string;
  harder?: string;
  videoKey?: string;
}) {
  const media = videoForExercise(exercise, videoKey);
  const preview = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(
    () => !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!media || !preview.current) return;
    if (playing) preview.current.play().catch(() => setPlaying(false));
    else preview.current.pause();
  }, [media, playing]);

  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) =>
      event.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [open]);

  if (!media) return null;
  return (
    <>
      <div className="exercise-media">
        <video
          ref={preview}
          src={media.src}
          poster={media.poster}
          muted
          loop
          playsInline
          preload="metadata"
          aria-label={`${media.title}. Lydløs videodemonstration.`}
        />
        <button
          type="button"
          className="video-open"
          onClick={() => setOpen(true)}
          aria-label={`Åbn video for ${exercise}`}
        >
          <i>▶</i> Se bevægelsen
        </button>
        <button
          type="button"
          className="video-pause"
          onClick={() => setPlaying(!playing)}
          aria-label={playing ? "Sæt animation på pause" : "Afspil animation"}
        >
          {playing ? "Ⅱ" : "▶"}
        </button>
      </div>
      {open && (
        <div
          className="modal-backdrop exercise-video-backdrop"
          role="presentation"
          onMouseDown={(event) =>
            event.target === event.currentTarget && setOpen(false)
          }
        >
          <section
            className="exercise-video-modal"
            role="dialog"
            aria-modal="true"
            aria-label={`Videoguide til ${exercise}`}
          >
            <button
              className="modal-close"
              onClick={() => setOpen(false)}
              aria-label="Luk video"
            >
              ×
            </button>
            <video
              src={media.src}
              poster={media.poster}
              controls
              autoPlay
              muted
              loop
            />
            <div>
              <p className="eyebrow">SÅDAN SER BEVÆGELSEN UD</p>
              <h2>{exercise}</h2>
              <p>{how}</p>
              <p className="video-easier">
                <b>Lettere variant:</b> {easier}
              </p>
              {harder && <p className="video-harder"><b>Når du er klar:</b> {harder}</p>}
              <small>
                Videoen viser bevægelsesfamilien. Følg din beskrevne variant,
                brug den lettere udgave ved behov, og stop ved smerte.
              </small>
              <a href={media.source} target="_blank" rel="noreferrer">
                Video: {media.credit} ↗
              </a>
            </div>
          </section>
        </div>
      )}
    </>
  );
}

type CoachMessage = { role: "user" | "assistant"; content: string; created_at?: string };

function CoachView({ csrf }: { csrf: string }) {
  const [messages, setMessages] = useState<CoachMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    api("/api/me").then((data) => setMessages(data.coachMessages || [])).catch(() => null);
  }, []);
  useEffect(() => {
    if (end.current && typeof end.current.scrollIntoView === "function") {
      end.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [messages, busy]);
  const ask = async (event: FormEvent) => {
    event.preventDefault();
    const value = question.trim();
    if (!value || busy) return;
    setQuestion("");
    setError("");
    setBusy(true);
    setMessages((current) => [...current, { role: "user", content: value }]);
    try {
      const result = await api("/api/coach", { method: "POST", body: JSON.stringify({ question: value }) }, csrf);
      setMessages((current) => [...current, { role: "assistant", content: result.answer }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Coachen kunne ikke svare lige nu.");
    } finally {
      setBusy(false);
    }
  };
  const suggestions = ["Hvordan gør jeg dagens træning lettere?", "Hvad kan jeg spise, når jeg er lækkersulten?", "Jeg mistede rytmen – hvordan starter jeg igen?"];
  return (
    <>
      <div className="page-heading compact"><div><p className="eyebrow">DIN AI-COACH · 12 SVAR OM DAGEN</p><h1>Spørg Fri Form.</h1><p>Få hjælp til at gøre din plan mere mulig – uden skældud, kure eller forbud.</p></div></div>
      <section className="coach-shell">
        <div className="coach-messages" aria-live="polite">
          {messages.length === 0 && <div className="coach-welcome"><i>✦</i><h2>Hvad fylder i dag?</h2><p>Jeg kender din ugeplan og kan hjælpe med lettere alternativer, madidéer og at komme tilbage efter en svær dag.</p><div>{suggestions.map((item) => <button onClick={() => setQuestion(item)} key={item}>{item}</button>)}</div></div>}
          {messages.map((message, index) => <article className={message.role} key={`${index}-${message.content.slice(0, 12)}`}><span>{message.role === "assistant" ? "FRI FORM" : "DIG"}</span><p>{message.content}</p></article>)}
          {busy && <article className="assistant thinking"><span>FRI FORM</span><p><i /> Tænker over et roligt, konkret svar…</p></article>}
          <div ref={end} />
        </div>
        {error && <p className="form-error">{error}</p>}
        <form className="coach-form" onSubmit={ask}><textarea rows={2} maxLength={800} value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Fx: Mine knæ er trætte i dag – hvad vælger jeg i stedet?" aria-label="Spørg Fri Form-coachen" /><button className="primary" disabled={busy || !question.trim()}>{busy ? "Svarer…" : "Send →"}</button></form>
        <small className="coach-disclaimer">Dit spørgsmål sendes uden navn og e-mail til OpenCode Go. Coachen giver generel livsstilsstøtte og kan tage fejl. Den erstatter ikke læge, fysioterapeut eller diætist.</small>
      </section>
    </>
  );
}

function ProgressView({
  plan,
  profile,
  csrf,
  checkins,
  setCheckins,
  resend,
  emailBusy,
  provider,
  onNextWeek,
}: {
  plan: Plan;
  profile: Profile;
  csrf: string;
  checkins: Checkin[];
  setCheckins: (v: Checkin[]) => void;
  resend: () => void;
  emailBusy: boolean;
  provider: string;
  onNextWeek: () => void;
}) {
  const [weight, setWeight] = useState(profile.weight);
  const [mood, setMood] = useState(3);
  const [saved, setSaved] = useState(false);
  const key = todayKey();
  const completed = checkins.filter((c) => c.completed).length;
  const days = new Set(checkins.filter((c) => c.completed).map((c) => c.day))
    .size;
  const weightPoints = checkins
    .filter((item) => typeof item.weight === "number")
    .sort((a, b) => a.day.localeCompare(b.day))
    .slice(-12);
  const weightValues = weightPoints.map((item) => Number(item.weight));
  const weightMin = weightValues.length ? Math.min(...weightValues) : profile.weight;
  const weightMax = weightValues.length ? Math.max(...weightValues) : profile.weight;
  const save = async () => {
    await api(
      "/api/checkin",
      {
        method: "POST",
        body: JSON.stringify({
          day: key,
          itemId: "daily-checkin",
          completed: true,
          weight,
          mood,
        }),
      },
      csrf,
    );
    const next = checkins.filter(
      (c) => !(c.day === key && c.item_id === "daily-checkin"),
    );
    next.push({
      day: key,
      item_id: "daily-checkin",
      completed: 1,
      weight,
      mood,
    });
    setCheckins(next);
    setSaved(true);
  };
  const deleteAccount = async () => {
    if (
      !window.confirm("Slet konto, profil, planer og alle check-ins permanent?")
    )
      return;
    await api("/api/account", { method: "DELETE" }, csrf);
    window.location.reload();
  };
  return (
    <>
      <div className="page-heading compact">
        <div>
          <p className="eyebrow">FREMGANG UDEN PRES</p>
          <h1>
            Se retningen.
            <br />
            Ikke kun tallet.
          </h1>
          <p>Energi, vaner og gentagelser tæller også som fremgang.</p>
        </div>
      </div>
      <section className="progress-chart">
        <div className="section-head"><div><p className="eyebrow">DIN RETNING</p><h2>Vægt over tid</h2></div><small>{weightPoints.length ? `${weightPoints.length} registreringer` : "Din første registrering bliver starten"}</small></div>
        {weightPoints.length > 0 ? (
          <div className="weight-bars">
            {weightPoints.map((point) => {
              const height = weightMax === weightMin ? 55 : 20 + ((Number(point.weight) - weightMin) / (weightMax - weightMin)) * 65;
              return <i key={`${point.day}-${point.item_id}`} style={{ height: `${height}%` }} title={`${point.day}: ${point.weight} kg`}><b>{point.weight}</b><small>{point.day.slice(5)}</small></i>;
            })}
          </div>
        ) : <p className="empty-chart">Vejning er valgfri. Når du gemmer check-ins, viser vi udviklingen her – uden røde tal eller dom.</p>}
      </section>
      <div className="stat-grid">
        <article>
          <span>✓</span>
          <b>{completed}</b>
          <small>små skridt klaret</small>
        </article>
        <article>
          <span>▦</span>
          <b>{days}</b>
          <small>aktive dage</small>
        </article>
        <article>
          <span>↘</span>
          <b>
            {Math.round((profile.weight - profile.targetWeight) * 10) / 10} kg
          </b>
          <small>dit første mål</small>
        </article>
      </div>
      <section className="checkin-card">
        <div>
          <p className="eyebrow">DAGENS CHECK-IN</p>
          <h2>Hvordan går det?</h2>
          <p>
            Vejning er valgfri. Brug samme tidspunkt og se på udviklingen over
            flere uger.
          </p>
        </div>
        <div className="checkin-form">
          <NumberField
            label="Vægt i dag"
            value={weight}
            min={40}
            max={300}
            unit="kg"
            onChange={setWeight}
          />
          <label>
            Energi i dag
            <div className="mood-scale">
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  className={mood === n ? "active" : ""}
                  key={n}
                  onClick={() => setMood(n)}
                >
                  {n}
                </button>
              ))}
            </div>
          </label>
          <button className="primary" onClick={save}>
            {saved ? "Gemt ✓" : "Gem check-in"}
          </button>
        </div>
      </section>
      {plan.program && plan.program.currentWeek < plan.program.totalWeeks && (
        <section className="reflection saved-reflection">
          <div><p className="eyebrow">UGENS REFLEKSION</p><h2>Gør næste uge klogere</h2><p>Dine svar bliver nu gemt og bruges af AI’en til at justere tempo, mad og aktivitet.</p></div>
          <button className="primary" onClick={onNextWeek}>Afslut uge {plan.program.currentWeek} →</button>
        </section>
      )}
      <section className="account-card">
        <div>
          <p className="eyebrow">DIN KONTO</p>
          <h2>Plan og persondata</h2>
          <p>
            Planen er lavet med{" "}
            {provider.startsWith("opencode")
              ? "OpenCode Go"
              : provider.startsWith("ollama")
                ? "lokal Gemma"
                : "den validerede reserveskabelon"}
            . Navn og e-mail sendes aldrig til AI-modellen.
          </p>
        </div>
        <div>
          <button className="secondary" onClick={resend} disabled={emailBusy}>
            {emailBusy ? "Sender…" : "Send hele planen på mail"}
          </button>
          <button className="danger" onClick={deleteAccount}>
            Slet min konto og alle data
          </button>
        </div>
      </section>
      <div className="safety-callout">
        <i>i</i>
        <p>
          <b>Generel vejledning.</b> {plan.medicalReminder}
        </p>
      </div>
    </>
  );
}

type AdminData = {
  counts: {
    users: number;
    newToday: number;
    new7Days: number;
    active7Days: number;
    active30Days: number;
    profiles: number;
    plans: number;
    emailsSent: number;
    completedSteps: number;
    weeklyReviews: number;
    coachAnswers: number;
    failedJobs: number;
    enrollmentLimit: number;
    enrolledNew: number;
    enrollmentRemaining: number;
  };
  recentUsers: {
    email: string;
    name: string;
    created_at: string;
    last_login_at: string | null;
    plans: number;
    checkins: number;
    program_days: number | null;
    program_ends_at: string | null;
  }[];
  aiUsage: {
    configured: boolean;
    model: string;
    active: null | {
      job_id: string;
      phase: string;
      started_at: string;
      completed_calls: number;
      total_calls: number;
    };
    fiveHours: UsageWindow;
    week: UsageWindow;
    month: UsageWindow;
    recentEvents: {
      phase: string;
      status: string;
      input_tokens: number;
      output_tokens: number;
      cache_read_tokens: number;
      estimated_cost_usd: number;
      started_at: string;
      finished_at: string | null;
      error_type: string | null;
    }[];
    authoritativeUrl: string;
    scope: string;
  };
  generatedAt: string;
};

type UsageWindow = {
  calls: number;
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheWriteTokens: number;
  costUsd: number;
  limitUsd: number;
  remainingUsd: number;
  releaseAt: string | null;
};

function AdminView() {
  const [data, setData] = useState<AdminData | null>(null);
  const [error, setError] = useState("");
  const [clock, setClock] = useState(Date.now());
  const load = () => {
    setError("");
    api("/api/admin/stats")
      .then(setData)
      .catch((err) =>
        setError(
          err instanceof Error
            ? err.message
            : "Statistikken kunne ikke hentes.",
        ),
      );
  };
  useEffect(() => {
    load();
    const poll = window.setInterval(load, 2000);
    const tick = window.setInterval(() => setClock(Date.now()), 1000);
    return () => {
      window.clearInterval(poll);
      window.clearInterval(tick);
    };
  }, []);
  if (error) return <div className="form-error">{error}</div>;
  if (!data)
    return (
      <div className="admin-loading">
        <span className="loader" />
        <p>Henter brugerstatistik…</p>
      </div>
    );
  const cards = [
    [
      "Testdeltagere",
      `${data.counts.enrolledNew}/${data.counts.enrollmentLimit}`,
      `${data.counts.enrollmentRemaining} pladser tilbage`,
    ],
    ["Brugere", data.counts.users, "Alle konti"],
    [
      "Nye i dag",
      data.counts.newToday,
      `${data.counts.new7Days} de sidste 7 dage`,
    ],
    [
      "Aktive",
      data.counts.active7Days,
      `${data.counts.active30Days} de sidste 30 dage`,
    ],
    ["Planer", data.counts.plans, `${data.counts.emailsSent} sendt på mail`],
    ["Fremgang", data.counts.completedSteps, "markerede skridt"],
    ["Uge-check-ins", data.counts.weeklyReviews, "gemte tilpasninger"],
    ["AI-coach", data.counts.coachAnswers, "svar til brugerne"],
    ["Fejlede jobs", data.counts.failedJobs, "kræver evt. kontrol"],
  ];
  return (
    <>
      <div className="page-heading compact admin-heading">
        <div>
          <p className="eyebrow">FRI FORM · ADMINISTRATION</p>
          <h1>Brugeroverblik</h1>
          <p>
            Driftsstatistik uden adgang til brugernes vægt, helbredssvar eller
            selve planindholdet.
          </p>
        </div>
        <button className="secondary" onClick={load}>
          ↻ Opdater
        </button>
      </div>
      <div className="admin-stats">
        {cards.map(([label, value, note]) => (
          <article key={String(label)}>
            <p>{label}</p>
            <b>{value}</b>
            <small>{note}</small>
          </article>
        ))}
      </div>
      <OpenCodeMeter usage={data.aiUsage} now={clock} />
      <section className="admin-users">
        <div className="section-head">
          <div>
            <p className="eyebrow">SENESTE KONTI</p>
            <h2>Brugere</h2>
          </div>
          <span>{data.counts.profiles} har udfyldt profil</span>
        </div>
        <div className="admin-table">
          <table>
            <thead>
              <tr>
                <th>Bruger</th>
                <th>Oprettet</th>
                <th>Seneste login</th>
                <th>Planer</th>
                <th>Forløb</th>
                <th>Skridt</th>
              </tr>
            </thead>
            <tbody>
              {data.recentUsers.map((item) => (
                <tr key={item.email}>
                  <td>
                    <b>{item.name}</b>
                    <small>{item.email}</small>
                  </td>
                  <td>{formatAdminDate(item.created_at)}</td>
                  <td>
                    {item.last_login_at
                      ? formatAdminDate(item.last_login_at)
                      : "—"}
                  </td>
                  <td>{item.plans}</td>
                  <td>
                    {item.program_days
                      ? programLabel(item.program_days)
                      : "Eksisterende"}
                  </td>
                  <td>{item.checkins}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <p className="admin-footnote">
        Opdateret {formatAdminDate(data.generatedAt)} · Kun tilgængelig for
        administratorens konto.
      </p>
    </>
  );
}

function OpenCodeMeter({
  usage,
  now,
}: {
  usage: AdminData["aiUsage"];
  now: number;
}) {
  const windows: [string, UsageWindow, string][] = [
    ["5 timer", usage.fiveHours, "Go-grænse $12"],
    ["7 dage", usage.week, "Go-grænse $30"],
    ["30 dage", usage.month, "Go-grænse $60"],
  ];
  const activeSeconds = usage.active
    ? Math.max(
        0,
        Math.floor((now - new Date(usage.active.started_at).getTime()) / 1000),
      )
    : 0;
  const activeTotal = usage.active?.total_calls || 5;
  return (
    <section className="ai-meter">
      <div className="ai-meter-head">
        <div>
          <p className="eyebrow">OPENCODE GO · LIVE</p>
          <h2>AI-forbrug og arbejde</h2>
          <p>{usage.scope}</p>
        </div>
        <div className={`ai-live ${usage.active ? "working" : ""}`}>
          <i />
          <span>
            <b>
              {usage.active
                ? "Arbejder nu"
                : usage.configured
                  ? "Klar"
                  : "Ikke konfigureret"}
            </b>
            <small>{usage.model}</small>
          </span>
        </div>
      </div>
      {usage.active && (
        <div className="ai-active-job">
          <div className="ai-orb">
            <span />
          </div>
          <div>
            <small>AKTUEL FASE · {Math.min(activeTotal, usage.active.completed_calls + 1)} AF {activeTotal}</small>
            <h3>{usage.active.phase}</h3>
            <p>
              OpenCode har arbejdet i {formatDuration(activeSeconds)}. Tallene
              opdateres automatisk.
            </p>
          </div>
          <b>{Math.min(100, (usage.active.completed_calls / activeTotal) * 100)}%</b>
        </div>
      )}
      <div className="usage-windows">
        {windows.map(([label, item, note]) => {
          const percent = Math.min(
            100,
            item.limitUsd ? (item.costUsd / item.limitUsd) * 100 : 0,
          );
          return (
            <article key={label}>
              <div>
                <span>{label}</span>
                <small>{note}</small>
              </div>
              <strong>
                {formatUsd(item.costUsd)} <em>/ {formatUsd(item.limitUsd)}</em>
              </strong>
              <div className="usage-bar">
                <i style={{ width: `${percent}%` }} />
              </div>
              <p>
                <b>{formatUsd(item.remainingUsd)}</b> tilbage · {item.calls}{" "}
                kald
              </p>
              <time>
                {item.releaseAt
                  ? `Næste forbrug frigives om ${countdown(item.releaseAt, now)}`
                  : "Perioden starter ved første kald"}
              </time>
            </article>
          );
        })}
      </div>
      <div className="ai-usage-bottom">
        <div>
          <p className="eyebrow">SENESTE AI-KALD</p>
          <div className="ai-event-list">
            {usage.recentEvents.length ? (
              usage.recentEvents.slice(0, 8).map((event, index) => (
                <article key={`${event.started_at}-${index}`}>
                  <i className={event.status} />
                  <span>
                    <b>{event.phase}</b>
                    <small>
                      {event.input_tokens.toLocaleString("da-DK")} ind ·{" "}
                      {event.output_tokens.toLocaleString("da-DK")} ud
                    </small>
                  </span>
                  <span>
                    <b>{formatUsd(event.estimated_cost_usd)}</b>
                    <small>
                      {event.finished_at
                        ? formatDuration(
                            Math.max(
                              0,
                              Math.round(
                                (new Date(event.finished_at).getTime() -
                                  new Date(event.started_at).getTime()) /
                                  1000,
                              ),
                            ),
                          )
                        : "live"}
                    </small>
                  </span>
                </article>
              ))
            ) : (
              <p className="empty-events">
                Første registrering kommer, næste gang Fri Form laver en plan.
              </p>
            )}
          </div>
        </div>
        <aside>
          <b>Hele OpenCode-kontoen</b>
          <p>
            OpenCode sender ikke kontoens samlede forbrug eller præcise
            reset-tider med API-svarene.
          </p>
          <a href={usage.authoritativeUrl} target="_blank" rel="noreferrer">
            Åbn den autoritative OpenCode-console ↗
          </a>
        </aside>
      </div>
    </section>
  );
}

function formatUsd(value: number) {
  return new Intl.NumberFormat("da-DK", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: value < 0.01 ? 4 : 2,
    maximumFractionDigits: value < 0.01 ? 4 : 2,
  }).format(value);
}

function formatDuration(totalSeconds: number) {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return hours
    ? `${hours}t ${minutes}m ${seconds}s`
    : minutes
      ? `${minutes}m ${seconds}s`
      : `${seconds}s`;
}

function countdown(value: string, now: number) {
  return formatDuration(
    Math.max(0, Math.ceil((new Date(value).getTime() - now) / 1000)),
  );
}

function formatAdminDate(value: string) {
  return new Intl.DateTimeFormat("da-DK", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "Europe/Copenhagen",
  }).format(new Date(value));
}

function PublicFooter() {
  return (
    <footer className="public-footer">
      <Brand />
      <div>
        <b>Fagligt udgangspunkt</b>
        <a
          href="https://foedevarestyrelsen.dk/kost-og-foedevarer/alt-om-mad/de-officielle-kostraad/kostraad-til-dig"
          target="_blank"
          rel="noreferrer"
        >
          De officielle Kostråd
        </a>
        <a
          href="https://www.sst.dk/vidensbase/forebyggelse/anbefalinger-om-fysisk-aktivitet"
          target="_blank"
          rel="noreferrer"
        >
          Sundhedsstyrelsens aktivitetsråd
        </a>
      </div>
      <div>
        <b>Privatliv</b>
        <p>
          Din konto kan slettes direkte i appen. Profilen sendes uden navn og
          e-mail til AI.
        </p>
      </div>
      <small>
        © 2026 Fri Form · En gratis tjeneste fra Dybbol.com · Ikke lægelig
        rådgivning.
      </small>
    </footer>
  );
}
