import { useQuery } from "@tanstack/react-query";
import { fetchUsers } from "../api/users";

export function UsersPage() {
  const { data: users, isPending, isError, error } = useQuery({
    queryKey: ["users"],
    queryFn: fetchUsers,
  });

  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold" style={{ color: "var(--navy-900)" }}>Users</h1>
      {isPending && <p style={{ color: "var(--text-muted)" }}>Loading…</p>}
      {isError && <p style={{ color: "var(--confid-fg)" }}>Failed to load users: {String(error)}</p>}
      {users && (
        <div className="overflow-hidden" style={{ border: "1px solid var(--border)", borderRadius: 6 }}>
          <table className="w-full text-sm">
            <thead className="text-left" style={{ background: "var(--bg-alt)", color: "var(--text-muted)" }}>
                <tr>
                  <th className="px-4 py-2 font-medium">ID</th>
                  <th className="px-4 py-2 font-medium">Name</th>
                  <th className="px-4 py-2 font-medium">Email</th>
                  <th className="px-4 py-2 font-medium">Sign-in</th>
                  <th className="px-4 py-2 font-medium">Role</th>
                  <th className="px-4 py-2 font-medium">Created</th>
                </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {users.map((u) => (
                <tr key={u.id}>
                  <td className="px-4 py-2">{u.id}</td>
                  <td className="px-4 py-2 font-medium">
                    {[u.first_name, u.last_name].filter(Boolean).join(" ") || u.username}
                  </td>
                  <td className="px-4 py-2 text-slate-600">{u.email}</td>
                  <td className="px-4 py-2 capitalize">{u.auth_provider}</td>
                  <td className="px-4 py-2 capitalize">{u.role}</td>
                  <td className="px-4 py-2 text-slate-500">{new Date(u.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
