import { useEffect, useState } from "react";
import QRCode from "qrcode";
import {
  CheckCircle2,
  Download,
  KeyRound,
  Loader2,
  ShieldCheck,
  UsersRound,
} from "lucide-react";
import { api, label } from "./types";
import { Dialog } from "./ui";
import "./review.css";

export type AccountSecurity = {
  enabled: boolean;
  enrollment_pending: boolean;
  recovery_codes_remaining: number;
};
type Notice = (message: string, error?: boolean) => void;
export function AccountSecurityDialog({ onClose }: { onClose: () => void }) {
  const [status, setStatus] = useState<AccountSecurity | null>(null);
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [enrollment, setEnrollment] = useState<{
    secret: string;
    uri: string;
  } | null>(null);
  const [qr, setQr] = useState("");
  const [recovery, setRecovery] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = () =>
    api<AccountSecurity>("/account/security").then(setStatus);
  useEffect(() => {
    refresh().catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    let active = true;
    setQr("");
    if (enrollment)
      QRCode.toDataURL(enrollment.uri, { width: 224, margin: 2 })
        .then((url) => {
          if (active) setQr(url);
        })
        .catch(() =>
          setError(
            "QR code could not be drawn. Enter the setup key in your authenticator.",
          ),
        );
    return () => {
      active = false;
    };
  }, [enrollment]);
  const submit = async (action: "enroll" | "confirm" | "disable") => {
    setBusy(true);
    setError("");
    try {
      if (action === "enroll") {
        setEnrollment(
          await api("/account/security/enroll", {
            method: "POST",
            body: JSON.stringify({ password, code: code || null }),
          }),
        );
        setPassword("");
        setCode("");
        setRecovery([]);
      } else if (action === "confirm") {
        const data = await api<{ recovery_codes: string[] }>(
          "/account/security/confirm",
          { method: "POST", body: JSON.stringify({ code }) },
        );
        setRecovery(data.recovery_codes);
        setEnrollment(null);
        setCode("");
      } else {
        await api("/account/security/disable", {
          method: "POST",
          body: JSON.stringify({ password, code: code || null }),
        });
        setPassword("");
        setCode("");
        setRecovery([]);
      }
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog
      title="Account security"
      subtitle="Protect your sign-in and engineering approvals."
      onClose={onClose}
    >
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      {!status && !error && (
        <p>
          <Loader2 className="spin" size={18} /> Loading security settings…
        </p>
      )}
      {status && (
        <>
          <div className="review-security-state">
            <ShieldCheck size={24} />
            <div>
              <b>
                {status.enabled
                  ? "Authenticator enabled"
                  : "Set up an authenticator"}
              </b>
              <p>
                {status.enabled
                  ? `${status.recovery_codes_remaining} recovery codes remain. Final approvals require a recent authenticator check.`
                  : "Use a standard authenticator app. Scan the QR code, then confirm its six-digit code."}
              </p>
            </div>
          </div>
          {recovery.length > 0 ? (
            <div className="recovery-panel">
              <h3>Keep your recovery codes</h3>
              <p>
                Each code works once if you lose your authenticator. This is the
                only time the codes are shown.
              </p>
              <div className="recovery-codes">
                {recovery.map((value) => (
                  <code key={value}>{value}</code>
                ))}
              </div>
              <button
                className="button secondary"
                onClick={() => {
                  const url = URL.createObjectURL(
                    new Blob(
                      [
                        "CAESAR recovery codes — keep privately\nEach code may be used once.\n\n" +
                          recovery.join("\n"),
                      ],
                      { type: "text/plain" },
                    ),
                  );
                  const link = document.createElement("a");
                  link.href = url;
                  link.download = "caesar-recovery-codes.txt";
                  link.click();
                  setTimeout(() => URL.revokeObjectURL(url), 1000);
                }}
              >
                <Download size={16} /> Save recovery codes
              </button>
            </div>
          ) : enrollment ? (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void submit("confirm");
              }}
            >
              <div className="authenticator-setup">
                {qr && (
                  <img
                    src={qr}
                    width={224}
                    height={224}
                    alt="Authenticator setup QR code"
                  />
                )}
                <div>
                  <h3>Scan in your authenticator</h3>
                  <p>Or enter this setup key manually:</p>
                  <code className="setup-key">{enrollment.secret}</code>
                  <small>
                    QR generated privately in this browser. Setup expires after
                    ten minutes.
                  </small>
                </div>
              </div>
              <label className="form-field">
                Six-digit authenticator code
                <input
                  required
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9 ]{6,8}"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
              </label>
              <button className="button primary" disabled={busy}>
                <CheckCircle2 size={16} /> Confirm authenticator
              </button>
            </form>
          ) : (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void submit(status.enabled ? "disable" : "enroll");
              }}
            >
              <label className="form-field">
                Current password
                <input
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </label>
              {status.enabled && (
                <label className="form-field">
                  Authenticator or recovery code
                  <input
                    autoComplete="one-time-code"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    maxLength={80}
                  />
                </label>
              )}
              <button className="button secondary" disabled={busy}>
                {busy ? (
                  <Loader2 className="spin" size={16} />
                ) : (
                  <KeyRound size={16} />
                )}
                {status.enabled
                  ? "Disable authenticator"
                  : "Set up authenticator"}
              </button>
            </form>
          )}
        </>
      )}
    </Dialog>
  );
}

type Person = {
  id: string;
  name: string;
  email: string;
  role: string;
  enabled: boolean;
  mfa_enabled?: boolean;
};
export function PeopleManager({ notify }: { notify: Notice }) {
  const [people, setPeople] = useState<Person[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [create, setCreate] = useState(false);
  const [editing, setEditing] = useState<Person | null>(null);
  const refresh = () => api<Person[]>("/system/people").then(setPeople);
  useEffect(() => {
    refresh().catch((e) => setError(e.message));
  }, []);
  return (
    <div className="page-content people-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">WORKSPACE ACCESS</span>
          <h1>
            People<span className="heading-dot">.</span>
          </h1>
          <p>
            Engineers prepare the work. An independent reviewer signs the final
            review issue.
          </p>
        </div>
        <button className="button primary" onClick={() => setCreate(true)}>
          <UsersRound size={17} /> Add account
        </button>
      </div>
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      <div className="panel">
        <div className="table-scroll">
          <table className="people-table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Role</th>
                <th>Authenticator</th>
                <th>Access</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {people.map((person) => (
                <tr key={person.id}>
                  <td>
                    <b>{person.name}</b>
                    <small>{person.email}</small>
                  </td>
                  <td>{label(person.role)}</td>
                  <td>{person.mfa_enabled ? "Enabled" : "Not set up"}</td>
                  <td>
                    <span
                      className={`badge ${person.enabled ? "green" : "neutral"}`}
                    >
                      {person.enabled ? "Enabled" : "Disabled"}
                    </span>
                  </td>
                  <td>
                    {!["admin", "local-engineer"].includes(person.id) && (
                      <button
                        className="button secondary small"
                        onClick={() => setEditing(person)}
                      >
                        Manage access
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="notice">
        <ShieldCheck size={18} />
        <span>
          Reviewers can read and approve; engineers can edit and sign sections;
          viewers can read. Changed access ends the affected account’s current
          sessions. Share a new account’s password privately.
        </span>
      </div>
      {(create || editing) && (
        <Dialog
          title={editing ? "Manage account access" : "Add workspace account"}
          subtitle={
            editing?.email || "Accounts stay within this hosting workspace."
          }
          onClose={() => {
            setCreate(false);
            setEditing(null);
          }}
        >
          <form
            onSubmit={async (event) => {
              event.preventDefault();
              const form = new FormData(event.currentTarget);
              setBusy(true);
              setError("");
              try {
                const role = String(form.get("role"));
                await api(
                  "/system/people" + (editing ? "/" + editing.id : ""),
                  {
                    method: editing ? "PATCH" : "POST",
                    body: JSON.stringify(
                      editing
                        ? {
                            role,
                            enabled: form.get("enabled") === "on",
                            reason: form.get("reason"),
                          }
                        : {
                            role,
                            name: form.get("name"),
                            email: form.get("email"),
                            password: form.get("password"),
                          },
                    ),
                  },
                );
                setCreate(false);
                setEditing(null);
                await refresh();
                notify(
                  editing
                    ? "Account access updated. Existing sessions ended."
                    : "Account created. Share the sign-in details privately.",
                );
              } catch (e) {
                const message = (e as Error).message;
                setError(message);
                notify(message, true);
              } finally {
                setBusy(false);
              }
            }}
          >
            {!editing && (
              <>
                <label className="form-field">
                  Name
                  <input name="name" required maxLength={100} />
                </label>
                <label className="form-field">
                  Email
                  <input
                    name="email"
                    type="email"
                    required
                    autoComplete="off"
                  />
                </label>
                <label className="form-field">
                  Password
                  <input
                    name="password"
                    type="password"
                    autoComplete="new-password"
                    minLength={12}
                    maxLength={1024}
                    required
                  />
                </label>
              </>
            )}
            <label className="form-field">
              Role
              <select
                aria-label="Role"
                name="role"
                defaultValue={editing?.role || "engineer"}
              >
                <option value="engineer">
                  Engineer — edit and review sections
                </option>
                <option value="reviewer">
                  Independent reviewer — read and approve
                </option>
                <option value="viewer">Viewer — read only</option>
              </select>
            </label>
            {editing && (
              <>
                <label className="check-row">
                  <input
                    name="enabled"
                    type="checkbox"
                    defaultChecked={editing.enabled}
                  />
                  Account enabled
                </label>
                <label className="form-field">
                  Reason for access change
                  <textarea
                    name="reason"
                    minLength={10}
                    maxLength={2000}
                    required
                  />
                </label>
              </>
            )}
            <div className="modal-footer">
              <button
                className="button secondary"
                type="button"
                onClick={() => {
                  setCreate(false);
                  setEditing(null);
                }}
              >
                Cancel
              </button>
              <button className="button primary" disabled={busy}>
                {busy && <Loader2 className="spin" size={16} />}
                {editing ? "Save access" : "Create account"}
              </button>
            </div>
          </form>
        </Dialog>
      )}
    </div>
  );
}
