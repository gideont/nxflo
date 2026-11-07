"use strict";
const API = "/bms_integration_hub/api";
const byId = id => document.getElementById(id);
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const date = value => value ? new Intl.DateTimeFormat("en-CA", {dateStyle:"medium", timeStyle:"short", timeZone:"UTC"}).format(new Date(value)) + " UTC" : "Not yet";
const state = {user:null, csrf:null, view:null, roles:[], projects:[], catalog:[], roleId:null, historyCursor:null, googleConfig:null};
const moduleLabels = {projects:"Project directory", requirements:"Requirements", planning:"Project planning", tasks:"Task lists", architecture:"Architecture", monitoring:"Monitoring"};

async function api(path, method = "GET", body, csrf = state.csrf) {
    const response = await fetch(API + path, {method, credentials:"same-origin", cache:"no-store", headers:{...(body !== undefined ? {"Content-Type":"application/json"} : {}), ...(method !== "GET" && csrf ? {"X-CSRF-Token":csrf} : {})}, ...(body !== undefined ? {body:JSON.stringify(body)} : {})});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) { const error = new Error(data.error || "The request could not be completed."); error.status = response.status; throw error; }
    return data;
}
function message(text, error = false) {
    const box = byId("workspace-message"); box.textContent = text; box.hidden = !text; box.classList.toggle("is-error", error);
}
function loginError(text) { byId("login-error").textContent = text; byId("login-error").hidden = !text; }
function handleError(error) {
    if (error.status === 401 && state.user) { showLogin("Your session ended. Please sign in again."); return; }
    const dialogError = byId("edit-dialog").querySelector(".dialog-error");
    if (byId("edit-dialog").open) { dialogError.textContent = error.message; dialogError.hidden = false; }
    else if (!state.user) loginError(error.message);
    else message(error.message, true);
}
function on(element, event, action) {
    element.addEventListener(event, e => Promise.resolve().then(() => action(e)).catch(handleError));
}
function ask(title, text) {
    return new Promise(resolve => {
        const dialog = byId("confirm-dialog"); byId("confirm-title").textContent = title; byId("confirm-message").textContent = text;
        dialog.returnValue = "cancel"; dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), {once:true}); dialog.showModal();
    });
}
function openDialog(html) {
    byId("edit-dialog-content").innerHTML = html;
    const error = byId("edit-dialog").querySelector(".dialog-error"); error.hidden = true; error.textContent = "";
    byId("edit-dialog").showModal();
    byId("edit-dialog-content").querySelectorAll("[data-close]").forEach(button => button.addEventListener("click", () => byId("edit-dialog").close()));
}
async function setupGoogle() {
    loginError(""); byId("retry-google").hidden = true;
    try {
        const config = await api("/auth/config"); state.googleConfig = config;
        if (!window.google?.accounts?.id) {
            await new Promise((resolve, reject) => {
                const old = document.getElementById("google-identity-script"); if (old) old.remove();
                const script = document.createElement("script"); script.id = "google-identity-script"; script.src = "https://accounts.google.com/gsi/client"; script.async = true;
                const timer = setTimeout(() => reject(new Error("Google sign-in could not load. Check your connection and try again.")), 15000);
                script.onload = () => {clearTimeout(timer); resolve();}; script.onerror = () => {clearTimeout(timer); reject(new Error("Google sign-in could not load. Please try again."));};
                document.head.append(script);
            });
        }
        window.google.accounts.id.initialize({client_id:config.client_id, nonce:config.nonce, callback:googleCredential, auto_select:false});
        const slot = byId("google-sign-in"); slot.replaceChildren();
        window.google.accounts.id.renderButton(slot, {type:"standard", theme:"outline", size:"large", text:"signin_with", shape:"rectangular", width:Math.min(396, Math.floor(slot.getBoundingClientRect().width))});
    } catch (error) { loginError(error.message); byId("retry-google").hidden = false; }
}
async function googleCredential(response) {
    loginError("");
    try {
        const data = await api("/auth/google", "POST", {credential:response.credential}, state.googleConfig.csrf_token);
        if (["rejected", "revoked"].includes(data.status)) { state.user = data.user; state.csrf = null; renderGate(); }
        else await loadSession();
    } catch (error) { loginError(error.message); byId("retry-google").hidden = false; }
}
let dashboard;
function workspaceDashboard() { return dashboard ||= window.createBMSWorkspace({api,state,esc,byId,on,openDialog,selectView,message}); }
function renderShell() {
    byId("login-shell").hidden = true; byId("workspace").hidden = false;
    byId("session-name").textContent = state.user.display_name;
    workspaceDashboard().initialize();
    document.querySelectorAll("[data-owner]").forEach(e => e.hidden = !state.user.is_owner);
}
function renderGate() {
    renderShell(); byId("workspace-nav").hidden = true; message("");
    const status = state.user.status;
    const copy = status === "pending" ? ["Awaiting administrator approval", "Your access request has been received. Your project administrator will review it before you can enter the workspace."] : status === "rejected" ? ["Access request declined", "Your request has not been approved. Please contact your project administrator if you need access."] : ["Workspace access revoked", "Your access is no longer active. Contact your project administrator if you need it restored."];
    byId("workspace-content").innerHTML = `<section class="account-gate"><span class="status-badge ${esc(status)}">${esc(status)}</span><h1>${copy[0]}</h1><p>${copy[1]}</p><p class="muted">Signed in as ${esc(state.user.email)}</p>${status === "pending" ? '<button id="refresh-access" class="primary-button" type="button">Check approval status</button>' : ""}</section>`;
    if (byId("refresh-access")) on(byId("refresh-access"), "click", () => loadSession());
}
async function loadSession(initial = false) {
    try {
        const data = await api("/me"); state.user = data.user; state.csrf = data.csrf_token;
        if (state.user.status !== "approved") { renderGate(); return; }
        renderShell(); byId("workspace-nav").hidden = false;
        await selectView(state.view || "home");
    } catch (error) { if (error.status === 401) await showLogin(initial ? "" : "Please sign in to continue."); else throw error; }
}
async function showLogin(text = "") {
    if(dashboard && state.user) dashboard.reset();
    state.user = null; state.csrf = null; state.view = null;
    byId("edit-dialog").close(); byId("confirm-dialog").close();
    byId("workspace-content").replaceChildren(); byId("workspace").hidden = true; byId("login-shell").hidden = false;
    await setupGoogle(); if (text) loginError(text);
}
async function selectView(view) {
    if (!state.user?.is_owner && ["users","roles","history"].includes(view)) view = "home";
    byId("admin-navigation").hidden = !state.user.is_owner || !["users","roles","history"].includes(view);
    state.view = view; message("");
    document.querySelectorAll("[data-view]").forEach(e => { if(e.dataset.view === view) e.setAttribute("aria-current", "page"); else e.removeAttribute("aria-current"); });
    byId("workspace-content").innerHTML = '<p class="muted" role="status">Loading workspace…</p>';
    if (view === "users") await renderUsers(); else if (view === "roles") await renderRoles(); else if (view === "history") await renderHistory(); else await workspaceDashboard().render(view);
}
async function renderUsers() {
    const [roles, projects] = await Promise.all([api("/admin/roles"), api("/admin/projects")]); state.roles = roles.roles; state.projects = projects.projects;
    byId("workspace-content").innerHTML = '<div class="page-heading"><div><p class="eyebrow">Access management</p><h1>Users</h1><p>Review requests, set one role per user, and assign project access.</p></div></div><form id="user-filters" class="filter-bar"><label>Search users<input id="user-query" type="search" placeholder="Name or email" maxlength="200"></label><label>Account status<select id="user-status"><option value="">All statuses</option><option>pending</option><option>approved</option><option>rejected</option><option>revoked</option></select></label><button class="secondary-button" type="submit">Search</button></form><div id="user-results" aria-live="polite"></div>';
    on(byId("user-filters"), "submit", e => {e.preventDefault(); return fetchUsers();}); on(byId("user-status"), "change", fetchUsers);
    await fetchUsers();
}
async function fetchUsers() {
    const data = await api("/admin/users?q=" + encodeURIComponent(byId("user-query").value) + "&status=" + encodeURIComponent(byId("user-status").value));
    byId("user-results").innerHTML = `<p class="result-count">${data.users.length} user${data.users.length === 1 ? "" : "s"}</p>` + (data.users.length ? '<div class="user-list">' + data.users.map(user => `<article class="user-card"><div class="user-card-top"><div class="user-identity"><h2>${esc(user.display_name)}</h2><p>${esc(user.email)}</p></div><span class="status-badge ${esc(user.status)}">${user.is_owner ? "Owner" : esc(user.status)}</span></div><dl class="user-dates"><div><dt>Role</dt><dd>${user.is_owner ? "Portal owner" : esc(user.role_name || "Not assigned")}</dd></div><div><dt>Created</dt><dd>${esc(date(user.created_at))}</dd></div><div><dt>Last login</dt><dd>${esc(date(user.last_login_at))}</dd></div><div><dt>Projects</dt><dd>${user.is_owner ? "All projects" : user.project_ids.length + " assigned"}</dd></div></dl>${user.is_owner ? '<p class="protected-note">Owner account · protected from access changes</p>' : `<button type="button" class="secondary-button" data-edit-user="${user.id}">Manage access</button>`}</article>`).join("") + '</div>' : '<div class="empty-state">No users match these filters.</div>');
    document.querySelectorAll("[data-edit-user]").forEach(button => on(button, "click", () => editUser(data.users.find(u => u.id === Number(button.dataset.editUser)))));
}
function editUser(user) {
    const transitions = {pending:["pending","approved","rejected"], approved:["approved","revoked"], rejected:["rejected","approved"], revoked:["revoked","approved"]};
    const selectedRole = user.role_id || state.roles.find(r => r.name === "Viewer")?.id;
    openDialog(`<h2 id="edit-dialog-title">Manage access</h2><p class="muted">${esc(user.display_name)} · ${esc(user.email)}</p><form id="user-access-form"><label>Account status<select name="status">${transitions[user.status].map(status => `<option ${status === user.status ? "selected" : ""}>${status}</option>`).join("")}</select></label><label>Role<select name="role_id"><option value="">No role assigned</option>${state.roles.map(role => `<option value="${role.id}" ${role.id === selectedRole ? "selected" : ""}>${esc(role.name)}</option>`).join("")}</select></label><p class="field-note">One role applies to all projects assigned to this user.</p><fieldset class="project-choices"><legend>Assigned projects</legend>${state.projects.length ? state.projects.map(project => `<label class="checkbox-label"><input type="checkbox" name="project_ids" value="${project.id}" ${user.project_ids.includes(project.id) ? "checked" : ""}><span>${esc(project.name)}</span></label>`).join("") : '<p class="muted">No projects yet. Add them in Projects before assigning access.</p>'}</fieldset><label>Reason or note <span class="muted">(optional)</span><textarea name="reason" maxlength="1000" rows="3"></textarea></label><div class="form-actions"><button type="button" class="secondary-button" data-close>Cancel</button><button type="submit" class="primary-button">Save access</button></div></form>`);
    on(byId("user-access-form"), "submit", async e => {
        e.preventDefault(); const form = new FormData(e.target); const button = e.submitter; button.disabled = true;
        try { await api("/admin/users/" + user.id, "PATCH", {status:form.get("status"), role_id:form.get("role_id") ? Number(form.get("role_id")) : null, project_ids:form.getAll("project_ids").map(Number), reason:form.get("reason")}); byId("edit-dialog").close(); await fetchUsers(); message("Access settings saved."); }
        finally {button.disabled = false;}
    });
}
async function renderRoles() {
    const [roles, catalog] = await Promise.all([api("/admin/roles"), api("/admin/permissions")]); state.roles = roles.roles; state.catalog = catalog.permissions;
    if (!state.roles.some(r => r.id === state.roleId)) state.roleId = state.roles[0]?.id || null;
    byId("workspace-content").innerHTML = `<div class="page-heading"><div><p class="eyebrow">Access management</p><h1>Roles &amp; permissions</h1><p>A role defines allowed actions. Project assignments determine where they apply.</p></div><button id="new-role" type="button" class="primary-button">New role</button></div><div class="role-picker"><label>Select a role<select id="role-picker">${state.roles.map(role => `<option value="${role.id}" ${role.id === state.roleId ? "selected" : ""}>${esc(role.name)} (${role.user_count} users)</option>`).join("")}</select></label></div><div id="role-editor"></div>`;
    on(byId("role-picker"), "change", e => {state.roleId = Number(e.target.value); renderRoleEditor();});
    on(byId("new-role"), "click", () => {state.roleId = null; byId("role-picker").selectedIndex = -1; renderRoleEditor();});
    renderRoleEditor();
}
function renderRoleEditor() {
    const role = state.roles.find(r => r.id === state.roleId); const keys = new Set(role?.permissions || []);
    byId("role-editor").innerHTML = `<form id="role-form" class="role-editor"><h2>${role ? "Edit role" : "Create a role"}</h2><div class="role-fields"><label>Role name<input name="name" required maxlength="80" value="${esc(role?.name || "")}"></label><label>Description<input name="description" maxlength="500" value="${esc(role?.description || "")}"></label></div><p class="impact-note">${role ? `Changes will affect <strong>${role.user_count} user${role.user_count === 1 ? "" : "s"}</strong> assigned to this role.` : "New roles start without permissions. Select the actions they need."}</p><table class="permission-matrix"><caption>Permission matrix</caption><thead><tr><th scope="col">Workspace</th>${["view","create","edit","delete"].map(action => `<th scope="col">${action}</th>`).join("")}</tr></thead><tbody>${Object.entries(moduleLabels).map(([module,label]) => `<tr><th scope="row">${label}</th>${["view","create","edit","delete"].map(action => {const key = module + "." + action; return `<td>${state.catalog.some(p => p.key === key) ? `<label class="permission-check"><input type="checkbox" name="permissions" value="${key}" aria-label="${action} ${label}" ${keys.has(key) ? "checked" : ""}><span class="mobile-action">${action}</span></label>` : '<span class="not-applicable" aria-label="Not available">—</span>'}</td>`;}).join("")}</tr>`).join("")}</tbody></table><p class="field-note">Create, edit, and delete require view access. Portal administration is reserved for the owner and cannot be granted through this matrix.</p><div class="form-actions">${role ? `<button id="delete-role" type="button" class="danger-button" ${role.user_count ? "disabled" : ""}>Delete role</button>` : ""}<button id="reload-role" type="button" class="secondary-button">Reload roles</button><button type="submit" class="primary-button">${role ? "Save permissions" : "Create role"}</button></div>${role?.user_count ? '<p class="field-note">Reassign all users before deleting this role.</p>' : ""}</form>`;
    const form = byId("role-form");
    on(form, "change", e => {if (e.target.name !== "permissions") return; const [module,action] = e.target.value.split("."); if (e.target.checked && action !== "view") form.querySelector(`input[value="${module}.view"]`).checked = true; if (!e.target.checked && action === "view") form.querySelectorAll(`input[value^="${module}."]`).forEach(box => box.checked = false);});
    on(byId("reload-role"), "click", renderRoles);
    if (role) on(byId("delete-role"), "click", async () => {if (!await ask("Delete this role?", `Delete ${role.name}? This role currently has no assigned users.`)) return; await api("/admin/roles/" + role.id, "DELETE", {}); state.roleId = null; await renderRoles(); message("Role deleted.");});
    on(form, "submit", async e => {
        e.preventDefault(); const fields = new FormData(form); const body = {name:fields.get("name"), description:fields.get("description"), permissions:fields.getAll("permissions")};
        if (role) {if (!await ask("Save role permissions?", `These changes apply to all ${role.user_count} user${role.user_count === 1 ? "" : "s"} assigned to ${role.name}.`)) return; body.version = role.version; body.confirm_affected_count = role.user_count;}
        e.submitter.disabled = true;
        try {const result = await api("/admin/roles" + (role ? "/" + role.id : ""), role ? "PATCH" : "POST", body); state.roleId = result.role.id; await renderRoles(); message("Role permissions saved.");} finally {e.submitter.disabled = false;}
    });
}
async function renderHistory() {
    state.historyCursor = null;
    byId("workspace-content").innerHTML = '<div class="page-heading"><div><p class="eyebrow">Access management</p><h1>Access history</h1><p>Approvals, role changes, project assignments, and access revocations.</p></div></div><div id="history-list" class="history-list"></div><button id="load-history" type="button" class="secondary-button">Load more</button>';
    on(byId("load-history"), "click", fetchHistory); await fetchHistory();
}
async function fetchHistory() {
    const data = await api("/admin/audit" + (state.historyCursor ? "?before=" + state.historyCursor : ""));
    if (!data.entries.length && !state.historyCursor) byId("history-list").innerHTML = '<div class="empty-state">No access changes recorded.</div>';
    byId("history-list").insertAdjacentHTML("beforeend", data.entries.map(entry => `<article class="history-card"><div class="history-heading"><h2>${esc(entry.action.replaceAll(".", " · ").replaceAll("_", " "))}</h2><time datetime="${esc(entry.created_at)}">${esc(date(entry.created_at))}</time></div><p>${esc(entry.actor_email || "System")} ${entry.subject_email ? "→ " + esc(entry.subject_email) : ""}</p>${entry.reason ? `<p class="history-reason">${esc(entry.reason)}</p>` : ""}<details><summary>View change details</summary><pre>${esc(JSON.stringify({before:entry.before, after:entry.after}, null, 2))}</pre></details></article>`).join(""));
    state.historyCursor = data.next_cursor; byId("load-history").hidden = !data.next_cursor;
}
document.querySelectorAll("[data-view]").forEach(button => on(button, "click", () => selectView(button.dataset.view)));
on(byId("sign-out"), "click", async () => {if (state.csrf) {try {await api("/auth/logout", "POST", {});} catch (error) {if(error.status !== 401) throw error;}} window.google?.accounts?.id?.disableAutoSelect(); await showLogin();});
on(byId("retry-google"), "click", setupGoogle);
setInterval(async () => {if (!state.user || !state.csrf || document.hidden) return; try {const data = await api("/me"); state.user = data.user; state.csrf = data.csrf_token; if (data.user.status !== "approved") renderGate();} catch(error) {handleError(error);}}, 60000);
loadSession(true).catch(handleError);
