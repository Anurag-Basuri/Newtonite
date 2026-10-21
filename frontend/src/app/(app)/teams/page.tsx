"use client";

import { useState } from "react";
import {
  Users,
  Plus,
  Shield,
  ShieldCheck,
  UserPlus,
  Trash2,
  CheckCircle2,
  AlertCircle,
  Building2,
  KeyRound,
  Hash,
} from "lucide-react";
import {
  useMe,
  useTeams,
  useTeamMembers,
  useCreateTeam,
  useAddTeamMember,
  useUpdateTeamMemberRole,
  useRemoveTeamMember,
  useSearchUsers,
} from "@/hooks/items";
import {
  Modal,
  Skeleton,
  ListSkeleton,
  ErrorState,
  Spinner,
  btnPrimary,
  btnSecondary,
  btnDanger,
  btnGhost,
} from "@/components/ui";
import type { TeamMembership, TeamMember } from "@/lib/types";

const ROLE_META: Record<
  "lead" | "member" | "viewer",
  { label: string; bg: string; text: string; border: string }
> = {
  lead: {
    label: "Lead",
    bg: "bg-purple-500/10 dark:bg-purple-500/20",
    text: "text-purple-700 dark:text-purple-300",
    border: "border-purple-500/30",
  },
  member: {
    label: "Member",
    bg: "bg-signal/10 dark:bg-signal/20",
    text: "text-signal",
    border: "border-signal/30",
  },
  viewer: {
    label: "Viewer",
    bg: "bg-muted/10 dark:bg-muted/20",
    text: "text-muted",
    border: "border-line",
  },
};

function RoleBadge({ role }: { role: "lead" | "member" | "viewer" }) {
  const meta = ROLE_META[role] || ROLE_META.member;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold tracking-wide capitalize ${meta.bg} ${meta.text} ${meta.border}`}
    >
      {role === "lead" && <ShieldCheck className="size-3" />}
      {role === "member" && <Shield className="size-3" />}
      {meta.label}
    </span>
  );
}

export default function TeamsPage() {
  const me = useMe();
  const teamsQuery = useTeams();

  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null);
  const [createTeamOpen, setCreateTeamOpen] = useState(false);
  const [addMemberOpen, setAddMemberOpen] = useState(false);
  const [memberToRemove, setMemberToRemove] = useState<TeamMember | null>(null);

  const teams = teamsQuery.data || [];
  const activeTeamId = selectedTeamId || teams[0]?.team_id || "";
  const activeTeam = teams.find((t) => t.team_id === activeTeamId) || teams[0];

  const membersQuery = useTeamMembers(activeTeamId);
  const members = membersQuery.data || [];

  const isOrgAdmin = Boolean(me.data?.is_org_admin);
  const isTeamLead = activeTeam?.role === "lead" || isOrgAdmin;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-ink">Teams & Organization</h1>
            {isOrgAdmin && (
              <span className="inline-flex items-center gap-1 rounded-full border border-purple-500/30 bg-purple-500/10 px-2 py-0.5 text-[11px] font-semibold text-purple-600 dark:text-purple-300">
                <ShieldCheck className="size-3" />
                Org Admin
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-muted">
            Manage operational units, key prefixes, and member access roles.
          </p>
        </div>

        {isOrgAdmin && (
          <button
            onClick={() => setCreateTeamOpen(true)}
            className={`${btnPrimary} self-start sm:self-auto`}
          >
            <Plus className="size-4" />
            <span>Create team</span>
          </button>
        )}
      </div>

      {teamsQuery.isLoading ? (
        <ListSkeleton rows={3} />
      ) : teamsQuery.isError ? (
        <ErrorState text="Failed to load teams." onRetry={() => teamsQuery.refetch()} />
      ) : teams.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-line bg-surface/50 p-12 text-center">
          <Building2 className="mx-auto size-10 text-muted" />
          <h2 className="mt-4 text-base font-semibold text-ink">No teams registered</h2>
          <p className="mt-1 text-xs text-muted">
            {isOrgAdmin
              ? "Get started by creating your organization's first team."
              : "You are not assigned to any teams yet."}
          </p>
          {isOrgAdmin && (
            <button
              onClick={() => setCreateTeamOpen(true)}
              className={`${btnPrimary} mt-4`}
            >
              <Plus className="size-4" />
              <span>Create team</span>
            </button>
          )}
        </div>
      ) : (
        /* Master-Detail Layout */
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* Left Column: Teams List */}
          <div className="space-y-3 lg:col-span-4">
            <h2 className="px-1 text-xs font-semibold uppercase tracking-wider text-muted">
              Registered Teams ({teams.length})
            </h2>
            <div className="space-y-2">
              {teams.map((t) => {
                const isSelected = t.team_id === activeTeamId;
                const name = t.team_name || t.team?.name || "Unnamed Team";
                const prefix = t.key_prefix || t.team?.key_prefix || "—";
                return (
                  <button
                    key={t.team_id}
                    onClick={() => setSelectedTeamId(t.team_id)}
                    className={`w-full text-left rounded-xl border p-4 transition-all ${
                      isSelected
                        ? "border-signal bg-signal/5 ring-1 ring-signal shadow-sm"
                        : "border-line bg-surface hover:border-line/80 hover:bg-canvas"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-ink truncate text-sm">{name}</span>
                          <span className="inline-flex items-center rounded border border-line bg-canvas px-1.5 py-0.5 text-[10px] font-mono font-medium text-muted">
                            {prefix}
                          </span>
                        </div>
                        {t.slug && (
                          <p className="mt-0.5 text-xs text-muted font-mono">{t.slug}</p>
                        )}
                      </div>
                      <RoleBadge role={t.role} />
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Right Column: Selected Team Detail & Member Roster */}
          <div className="space-y-6 lg:col-span-8">
            {activeTeam && (
              <>
                {/* Team Info Card */}
                <div className="rounded-2xl border border-line bg-surface p-6 shadow-xs">
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <div className="flex items-center gap-2.5">
                        <h2 className="text-xl font-bold tracking-tight text-ink">
                          {activeTeam.team_name || activeTeam.team?.name}
                        </h2>
                        <span className="inline-flex items-center gap-1 rounded-md border border-signal/20 bg-signal/10 px-2.5 py-0.5 text-xs font-mono font-semibold text-signal">
                          <Hash className="size-3" />
                          {activeTeam.key_prefix || activeTeam.team?.key_prefix}
                        </span>
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-4 text-xs text-muted">
                        <span className="flex items-center gap-1">
                          <KeyRound className="size-3.5" />
                          Slug: <span className="font-mono text-ink">{activeTeam.slug || activeTeam.team_id}</span>
                        </span>
                        <span className="flex items-center gap-1">
                          <Shield className="size-3.5" />
                          Your Access: <span className="capitalize font-medium text-ink">{activeTeam.role}</span>
                        </span>
                      </div>
                    </div>

                    {isOrgAdmin && (
                      <button
                        onClick={() => setAddMemberOpen(true)}
                        className={`${btnPrimary} shrink-0`}
                      >
                        <UserPlus className="size-4" />
                        <span>Add member</span>
                      </button>
                    )}
                  </div>
                </div>

                {/* Team Members Roster */}
                <div className="rounded-2xl border border-line bg-surface shadow-xs overflow-hidden">
                  <div className="flex items-center justify-between border-b border-line px-6 py-4">
                    <div>
                      <h3 className="font-semibold text-ink text-sm">Team Roster</h3>
                      <p className="text-xs text-muted">
                        Members who can be assigned and work on tickets for this queue.
                      </p>
                    </div>
                    <span className="rounded-full border border-line bg-canvas px-2.5 py-0.5 text-xs font-semibold text-muted">
                      {members.length} {members.length === 1 ? "member" : "members"}
                    </span>
                  </div>

                  {membersQuery.isLoading ? (
                    <div className="p-6">
                      <ListSkeleton rows={3} />
                    </div>
                  ) : membersQuery.isError ? (
                    <div className="p-6">
                      <ErrorState
                        text="Failed to load team members."
                        onRetry={() => membersQuery.refetch()}
                      />
                    </div>
                  ) : members.length === 0 ? (
                    <div className="p-8 text-center">
                      <Users className="mx-auto size-8 text-muted" />
                      <p className="mt-2 text-sm text-muted">No members assigned to this team.</p>
                      {isOrgAdmin && (
                        <button
                          onClick={() => setAddMemberOpen(true)}
                          className={`${btnSecondary} mt-3 text-xs`}
                        >
                          <UserPlus className="size-3.5" />
                          <span>Add first member</span>
                        </button>
                      )}
                    </div>
                  ) : (
                    <div className="divide-y divide-line">
                      {members.map((m) => {
                        const name = m.user?.name || m.name || "Unknown";
                        const email = m.user?.email || m.email || "";
                        const userId = m.user_id || m.user?.id || m.id;
                        const initials = name
                          .split(" ")
                          .map((n) => n[0])
                          .join("")
                          .slice(0, 2)
                          .toUpperCase();

                        return (
                          <div
                            key={m.id || userId}
                            className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between hover:bg-canvas/50 transition-colors"
                          >
                            <div className="flex items-center gap-3">
                              <div className="flex size-9 items-center justify-center rounded-full bg-signal/10 text-signal font-semibold text-xs border border-signal/20">
                                {initials}
                              </div>
                              <div>
                                <div className="flex items-center gap-2">
                                  <span className="font-semibold text-ink text-sm">{name}</span>
                                  {me.data?.user.id === userId && (
                                    <span className="rounded bg-canvas border border-line px-1.5 py-0.2 text-[10px] font-medium text-muted">
                                      You
                                    </span>
                                  )}
                                </div>
                                {email && <p className="text-xs text-muted">{email}</p>}
                              </div>
                            </div>

                            <div className="flex items-center gap-3 self-end sm:self-auto">
                              {isOrgAdmin ? (
                                <MemberRoleEditor
                                  teamId={activeTeamId}
                                  userId={userId}
                                  currentRole={m.role}
                                />
                              ) : (
                                <RoleBadge role={m.role} />
                              )}

                              {isOrgAdmin && (
                                <button
                                  onClick={() => setMemberToRemove(m)}
                                  aria-label={`Remove ${name}`}
                                  className="flex size-8 items-center justify-center rounded-lg text-muted hover:text-p0 hover:bg-p0/10 transition-colors"
                                  title="Remove member"
                                >
                                  <Trash2 className="size-4" />
                                </button>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Create Team Modal */}
      <CreateTeamModal
        open={createTeamOpen}
        onClose={() => setCreateTeamOpen(false)}
        onCreated={(newTeamId) => {
          setSelectedTeamId(newTeamId);
          setCreateTeamOpen(false);
        }}
      />

      {/* Add Member Modal */}
      {activeTeam && (
        <AddMemberModal
          open={addMemberOpen}
          teamId={activeTeamId}
          teamName={activeTeam.team_name || activeTeam.team?.name || "Team"}
          existingMemberUserIds={members.map((m) => m.user_id || m.user?.id || m.id)}
          onClose={() => setAddMemberOpen(false)}
        />
      )}

      {/* Remove Member Confirmation Dialog */}
      {memberToRemove && activeTeam && (
        <RemoveMemberModal
          open={Boolean(memberToRemove)}
          teamId={activeTeamId}
          member={memberToRemove}
          onClose={() => setMemberToRemove(null)}
        />
      )}
    </div>
  );
}

/** Inline select for updating member role */
function MemberRoleEditor({
  teamId,
  userId,
  currentRole,
}: {
  teamId: string;
  userId: string;
  currentRole: "viewer" | "member" | "lead";
}) {
  const updateRole = useUpdateTeamMemberRole(teamId);
  const [role, setRole] = useState(currentRole);

  const handleChange = async (newRole: "viewer" | "member" | "lead") => {
    setRole(newRole);
    try {
      await updateRole.mutateAsync({ userId, role: newRole });
    } catch {
      setRole(currentRole);
    }
  };

  return (
    <div className="flex items-center gap-1.5">
      <select
        value={role}
        disabled={updateRole.isPending}
        onChange={(e) => handleChange(e.target.value as "viewer" | "member" | "lead")}
        className="rounded-lg border border-line bg-canvas px-2.5 py-1 text-xs font-semibold text-ink focus:border-signal focus:outline-none disabled:opacity-50"
      >
        <option value="viewer">Viewer</option>
        <option value="member">Member</option>
        <option value="lead">Lead</option>
      </select>
      {updateRole.isPending && <Spinner className="size-3 text-signal" />}
    </div>
  );
}

/** Create Team Modal dialog */
function CreateTeamModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (teamId: string) => void;
}) {
  const createTeam = useCreateTeam();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [keyPrefix, setKeyPrefix] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleNameChange = (val: string) => {
    setName(val);
    if (!slug || slug === name.toLowerCase().replace(/[^a-z0-9]/g, "-")) {
      setSlug(
        val
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/^-|-$/g, "")
      );
    }
    if (!keyPrefix || keyPrefix === name.slice(0, 3).toUpperCase()) {
      setKeyPrefix(val.replace(/[^a-zA-Z]/g, "").slice(0, 4).toUpperCase());
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!name.trim()) {
      setError("Team name is required.");
      return;
    }
    if (!slug.trim()) {
      setError("Slug is required.");
      return;
    }
    if (!keyPrefix.trim() || keyPrefix.length < 2) {
      setError("Key prefix must be at least 2 characters.");
      return;
    }

    try {
      const res = await createTeam.mutateAsync({
        name: name.trim(),
        slug: slug.trim().toLowerCase(),
        key_prefix: keyPrefix.trim().toUpperCase(),
      });
      setName("");
      setSlug("");
      setKeyPrefix("");
      onCreated(res?._id || res?.id || "");
    } catch (err: any) {
      setError(err?.detail || err?.title || "Failed to create team. Ensure key prefix and slug are unique.");
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Create New Team"
      description="Create a new operational division with its own ticket queue and atomic key counter."
    >
      <form onSubmit={handleSubmit} className="space-y-4 pt-2">
        {error && (
          <div className="flex items-center gap-2 rounded-xl border border-p0/30 bg-p0/10 p-3 text-xs text-p0">
            <AlertCircle className="size-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div>
          <label className="block text-xs font-semibold text-ink">Team Name</label>
          <input
            type="text"
            required
            placeholder="e.g. Security & Fraud"
            value={name}
            onChange={(e) => handleNameChange(e.target.value)}
            className="mt-1 w-full rounded-xl border border-line bg-canvas px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-signal focus:outline-none"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-semibold text-ink">Slug</label>
            <input
              type="text"
              required
              placeholder="e.g. security-fraud"
              value={slug}
              onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
              className="mt-1 w-full rounded-xl border border-line bg-canvas px-3 py-2 text-sm font-mono text-ink placeholder:text-muted focus:border-signal focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-ink">Key Prefix</label>
            <input
              type="text"
              required
              maxLength={8}
              placeholder="e.g. SEC"
              value={keyPrefix}
              onChange={(e) => setKeyPrefix(e.target.value.toUpperCase().replace(/[^A-Z]/g, ""))}
              className="mt-1 w-full rounded-xl border border-line bg-canvas px-3 py-2 text-sm font-mono font-semibold uppercase text-ink placeholder:text-muted focus:border-signal focus:outline-none"
            />
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 pt-4">
          <button type="button" onClick={onClose} className={btnGhost}>
            Cancel
          </button>
          <button
            type="submit"
            disabled={createTeam.isPending}
            className={btnPrimary}
          >
            {createTeam.isPending ? <Spinner className="size-4" /> : <Plus className="size-4" />}
            <span>Create Team</span>
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** Add Member Modal dialog */
function AddMemberModal({
  open,
  teamId,
  teamName,
  existingMemberUserIds,
  onClose,
}: {
  open: boolean;
  teamId: string;
  teamName: string;
  existingMemberUserIds: string[];
  onClose: () => void;
}) {
  const addMember = useAddTeamMember(teamId);
  const [searchQuery, setSearchQuery] = useState("");
  const usersQuery = useSearchUsers(searchQuery);

  const [selectedUserId, setSelectedUserId] = useState<string>("");
  const [role, setRole] = useState<"viewer" | "member" | "lead">("member");
  const [error, setError] = useState<string | null>(null);

  const candidateUsers = (usersQuery.data || []).filter(
    (u) => !existingMemberUserIds.includes(u.id)
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!selectedUserId) {
      setError("Please select a user to add.");
      return;
    }

    try {
      await addMember.mutateAsync({
        user_id: selectedUserId,
        role,
      });
      setSelectedUserId("");
      onClose();
    } catch (err: any) {
      setError(err?.detail || err?.title || "Failed to add member.");
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Add Member to ${teamName}`}
      description="Select an existing user from the organization and assign their access role."
    >
      <form onSubmit={handleSubmit} className="space-y-4 pt-2">
        {error && (
          <div className="flex items-center gap-2 rounded-xl border border-p0/30 bg-p0/10 p-3 text-xs text-p0">
            <AlertCircle className="size-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div>
          <label className="block text-xs font-semibold text-ink">Select User</label>
          <input
            type="text"
            placeholder="Filter users by name or email..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="mt-1 mb-2 w-full rounded-xl border border-line bg-canvas px-3 py-1.5 text-xs text-ink placeholder:text-muted focus:border-signal focus:outline-none"
          />

          {usersQuery.isLoading ? (
            <div className="p-3">
              <Skeleton className="h-10 w-full" />
            </div>
          ) : candidateUsers.length === 0 ? (
            <div className="rounded-xl border border-line bg-canvas/50 p-4 text-center text-xs text-muted">
              {usersQuery.data?.length === 0
                ? "No matching users found."
                : "All matching users are already members of this team."}
            </div>
          ) : (
            <div className="max-h-48 space-y-1 overflow-y-auto rounded-xl border border-line bg-canvas p-1">
              {candidateUsers.map((u) => {
                const isSelected = selectedUserId === u.id;
                return (
                  <button
                    key={u.id}
                    type="button"
                    onClick={() => setSelectedUserId(u.id)}
                    className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs transition-colors ${
                      isSelected
                        ? "bg-signal text-white font-medium"
                        : "text-ink hover:bg-surface"
                    }`}
                  >
                    <div>
                      <p className="font-semibold">{u.name}</p>
                      <p className={`text-[11px] ${isSelected ? "text-white/80" : "text-muted"}`}>
                        {u.email}
                      </p>
                    </div>
                    {isSelected && <CheckCircle2 className="size-4 shrink-0" />}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div>
          <label className="block text-xs font-semibold text-ink">Role</label>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as "viewer" | "member" | "lead")}
            className="mt-1 w-full rounded-xl border border-line bg-canvas px-3 py-2 text-sm text-ink focus:border-signal focus:outline-none"
          >
            <option value="member">Member (Can claim, edit, transition, comment)</option>
            <option value="lead">Lead (Can assign, approve, edit P0, manage workflows)</option>
            <option value="viewer">Viewer (Read-only access)</option>
          </select>
        </div>

        <div className="flex items-center justify-end gap-2 pt-4">
          <button type="button" onClick={onClose} className={btnGhost}>
            Cancel
          </button>
          <button
            type="submit"
            disabled={addMember.isPending || !selectedUserId}
            className={btnPrimary}
          >
            {addMember.isPending ? <Spinner className="size-4" /> : <UserPlus className="size-4" />}
            <span>Add Member</span>
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** Remove Member confirmation dialog */
function RemoveMemberModal({
  open,
  teamId,
  member,
  onClose,
}: {
  open: boolean;
  teamId: string;
  member: TeamMember;
  onClose: () => void;
}) {
  const removeMember = useRemoveTeamMember(teamId);
  const [error, setError] = useState<string | null>(null);

  const name = member.user?.name || member.name || "this member";
  const userId = member.user_id || member.user?.id || member.id;

  const handleConfirm = async () => {
    setError(null);
    try {
      await removeMember.mutateAsync(userId);
      onClose();
    } catch (err: any) {
      setError(err?.detail || err?.title || "Failed to remove member.");
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Remove Team Member"
      description={`Are you sure you want to remove ${name} from this team? They will immediately lose access to team tickets and queues.`}
    >
      <div className="space-y-4 pt-2">
        {error && (
          <div className="flex items-center gap-2 rounded-xl border border-p0/30 bg-p0/10 p-3 text-xs text-p0">
            <AlertCircle className="size-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="flex items-center justify-end gap-2 pt-4">
          <button type="button" onClick={onClose} className={btnGhost}>
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={removeMember.isPending}
            className={btnDanger}
          >
            {removeMember.isPending ? <Spinner className="size-4" /> : <Trash2 className="size-4" />}
            <span>Remove Member</span>
          </button>
        </div>
      </div>
    </Modal>
  );
}
