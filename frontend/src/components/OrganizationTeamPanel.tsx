/**
 * Team management for one organization (org admin): members, invites.
 */

import { useCallback, useEffect, useState } from "react";
import {
  createOrganizationInvite,
  fetchOrganizationInvites,
  fetchOrganizationMembers,
  removeOrganizationMember,
  updateOrganizationMemberRole,
  type OrganizationInviteResponse,
  type OrganizationMemberResponse,
} from "../lib/organizationTeam";

type OrganizationTeamPanelProps = {
  apiBase: string;
  organizationId: string;
  organizationName: string;
};

export function OrganizationTeamPanel({
  apiBase,
  organizationId,
  organizationName,
}: OrganizationTeamPanelProps) {
  const [members, setMembers] = useState<OrganizationMemberResponse[]>([]);
  const [invites, setInvites] = useState<OrganizationInviteResponse[]>([]);
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
      const [m, i] = await Promise.all([
        fetchOrganizationMembers(apiBase, organizationId),
        fetchOrganizationInvites(apiBase, organizationId),
      ]);
      setMembers(m);
      setInvites(i);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [apiBase, organizationId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <section className="card card--nested">
      <h3>Team — {organizationName}</h3>
      <p className="card-subtitle">Invite colleagues and manage roles for this organization.</p>
      {error ? <p className="error">{error}</p> : null}
      {loading ? <p className="hint">Loading team…</p> : null}

      <label className="field">
        <span>Invite by email</span>
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
              await createOrganizationInvite(apiBase, organizationId, inviteEmail.trim(), inviteRole);
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

      <h4 className="team-subheading">Members</h4>
      {members.length === 0 && !loading ? <p className="hint">No members yet.</p> : null}
      <ul className="team-list">
        {members.map((m) => (
          <li key={m.user_id} className="team-list__row">
            <span>
              <strong>{m.email}</strong> —{" "}
              <select
                value={m.role}
                onChange={(e) => {
                  void (async () => {
                    try {
                      await updateOrganizationMemberRole(
                        apiBase,
                        organizationId,
                        m.user_id,
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
            </span>
            <button
              type="button"
              className="secondary table-inline-btn"
              onClick={() => {
                if (!window.confirm(`Remove ${m.email} from this organization?`)) return;
                void (async () => {
                  try {
                    await removeOrganizationMember(apiBase, organizationId, m.user_id);
                    await reload();
                  } catch (err) {
                    setError(err instanceof Error ? err.message : String(err));
                  }
                })();
              }}
            >
              Remove
            </button>
          </li>
        ))}
      </ul>

      {invites.length > 0 ? (
        <>
          <h4 className="team-subheading">Pending invites</h4>
          <ul className="team-list">
            {invites.map((inv) => (
              <li key={inv.id}>
                {inv.email} — {inv.role} (expires {new Date(inv.expires_at).toLocaleDateString()})
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}
