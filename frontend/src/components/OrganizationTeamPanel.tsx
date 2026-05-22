/**
 * Organization team directory (all members) plus admin invite/role controls.
 */

import { useCallback, useEffect, useState } from "react";
import {
  createOrganizationInvite,
  deactivateOrganizationMember,
  fetchOrganizationTeam,
  updateOrganizationMemberRole,
  type OrganizationTeamRosterRow,
} from "../lib/organizationTeam";

type OrganizationTeamPanelProps = {
  apiBase: string;
  organizationId: string;
  organizationName: string;
  /** Org admin may invite, change roles, and deactivate members. */
  canManage: boolean;
};

function formatRole(role: string): string {
  if (role === "org_admin") return "Org admin";
  if (role === "member") return "Member";
  if (role === "viewer") return "Viewer";
  return role;
}

function statusClass(status: string): string {
  return `team-status team-status--${status.replace(/[^a-z0-9_]+/gi, "_")}`;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString();
}

export function OrganizationTeamPanel({
  apiBase,
  organizationId,
  organizationName,
  canManage,
}: OrganizationTeamPanelProps) {
  const [roster, setRoster] = useState<OrganizationTeamRosterRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [inviteBusy, setInviteBusy] = useState(false);
  const [inviteMessage, setInviteMessage] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await fetchOrganizationTeam(apiBase, organizationId);
      setRoster(rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [apiBase, organizationId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const activeMemberCount = roster.filter(
    (r) => r.row_type === "member" && r.status === "active",
  ).length;
  const inviteCount = roster.filter((r) => r.row_type === "invite").length;

  return (
    <section className="card card--nested">
      <h3>Team — {organizationName}</h3>
      <p className="card-subtitle">
        {canManage
          ? "Everyone in this organization can see the roster below. Org admins can invite, change roles, and deactivate members."
          : "Members and pending invitations for this organization. Invites expire after 7 days."}
      </p>
      {error ? <p className="error">{error}</p> : null}
      {loading ? <p className="hint">Loading team…</p> : null}

      {!loading && roster.length === 0 ? <p className="hint">No members yet.</p> : null}

      {roster.length > 0 ? (
        <div className="table-wrap">
          <table className="doc-table team-directory-table">
            <thead>
              <tr>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
                <th>Joined</th>
                <th>Invited</th>
                <th>Expires</th>
                <th>Deactivated by</th>
                {canManage ? <th>Actions</th> : null}
              </tr>
            </thead>
            <tbody>
              {roster.map((row) => {
                const isActiveMember = row.row_type === "member" && row.status === "active";
                return (
                  <tr
                    key={row.row_type === "member" ? `m-${row.user_id}` : `i-${row.invite_id}`}
                    className={row.status === "deactivated" ? "team-row--deactivated" : undefined}
                  >
                    <td>
                      <strong>{row.email}</strong>
                      {row.row_type === "invite" ? (
                        <span className="hint" style={{ display: "block", marginTop: "0.15rem" }}>
                          Invitation
                        </span>
                      ) : null}
                    </td>
                    <td>
                      {canManage && isActiveMember && row.user_id ? (
                        <select
                          value={row.role}
                          aria-label={`Role for ${row.email}`}
                          onChange={(e) => {
                            void (async () => {
                              try {
                                await updateOrganizationMemberRole(
                                  apiBase,
                                  organizationId,
                                  row.user_id!,
                                  e.target.value,
                                );
                                await reload();
                              } catch (err) {
                                setError(err instanceof Error ? err.message : String(err));
                              }
                            })();
                          }}
                        >
                          <option value="org_admin">Org admin</option>
                          <option value="member">Member</option>
                          <option value="viewer">Viewer</option>
                        </select>
                      ) : (
                        formatRole(row.role)
                      )}
                    </td>
                    <td>
                      <span className={statusClass(row.status)}>{row.status_label}</span>
                    </td>
                    <td className="hint" style={{ fontSize: "0.82rem" }}>
                      {row.row_type === "member" ? formatDate(row.joined_at) : "—"}
                    </td>
                    <td className="hint" style={{ fontSize: "0.82rem" }}>
                      {row.row_type === "invite" ? formatDate(row.invited_at) : "—"}
                    </td>
                    <td className="hint" style={{ fontSize: "0.82rem" }}>
                      {row.row_type === "invite" ? formatDate(row.expires_at) : "—"}
                    </td>
                    <td className="hint" style={{ fontSize: "0.82rem" }}>
                      {row.deactivated_by_email ?? "—"}
                    </td>
                    {canManage ? (
                      <td>
                        {isActiveMember && row.user_id ? (
                          <button
                            type="button"
                            className="secondary table-inline-btn"
                            onClick={() => {
                              if (
                                !window.confirm(
                                  `Deactivate ${row.email}? They will lose access to this organization.`,
                                )
                              ) {
                                return;
                              }
                              void (async () => {
                                try {
                                  await deactivateOrganizationMember(
                                    apiBase,
                                    organizationId,
                                    row.user_id!,
                                  );
                                  await reload();
                                } catch (err) {
                                  setError(err instanceof Error ? err.message : String(err));
                                }
                              })();
                            }}
                          >
                            Deactivate
                          </button>
                        ) : (
                          <span className="hint">—</span>
                        )}
                      </td>
                    ) : null}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      {!loading ? (
        <p className="hint" style={{ marginTop: "0.75rem" }}>
          {activeMemberCount} active member{activeMemberCount === 1 ? "" : "s"}
          {inviteCount > 0
            ? ` · ${inviteCount} open invitation${inviteCount === 1 ? "" : "s"}`
            : ""}
        </p>
      ) : null}

      {canManage ? (
        <>
          <h4 className="team-subheading">Invite someone</h4>
          <label className="field">
            <span>Email</span>
            <input
              type="email"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder="colleague@company.com"
            />
          </label>
          <label className="field">
            <span>Role</span>
            <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)}>
              <option value="org_admin">Org admin</option>
              <option value="member">Member (upload &amp; review)</option>
              <option value="viewer">Viewer (read only)</option>
            </select>
          </label>
          {inviteMessage ? <p className="success">{inviteMessage}</p> : null}
          <button
            type="button"
            className="primary"
            disabled={inviteBusy || !inviteEmail.trim()}
            onClick={() => {
              void (async () => {
                setInviteBusy(true);
                setInviteMessage(null);
                try {
                  await createOrganizationInvite(
                    apiBase,
                    organizationId,
                    inviteEmail.trim(),
                    inviteRole,
                  );
                  setInviteMessage(
                    "Invite sent. Check the recipient inbox, or Mailpit at http://127.0.0.1:8025 when running ./scripts/dev.sh.",
                  );
                  setInviteEmail("");
                  await reload();
                } catch (e) {
                  setError(e instanceof Error ? e.message : String(e));
                } finally {
                  setInviteBusy(false);
                }
              })();
            }}
          >
            {inviteBusy ? "Sending…" : "Send invite"}
          </button>
        </>
      ) : null}
    </section>
  );
}
