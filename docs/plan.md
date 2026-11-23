# Makerspace Equipment Loan Requests

## Summary
A community makerspace needs a lightweight way for members to request equipment loans and for an approver to approve or reject each request with a mandatory note. Members submit requests, approvers decide, and viewers read-only observe, with everyone able to see the current status and full decision history. The outcome is a single FastAPI app on the `form-workflow` template backed by Firestore, with a no-login role switcher.

## Similar initiatives
- **P-t01 — Another POC project (tracker)** (`fastapi-crud`): A generic tracker POC; this plan reuses the POC banner and simple server-rendered pattern but adds a true approval workflow with status history rather than plain CRUD.
- **LP-012 — Laptop loan register** (`nextjs-crud`): Also a loan/borrow domain; we reuse the loan request concept but stay on FastAPI/Firestore with an approval step and no inventory tracking, and on a different stack.
- **LP-007 — Maintenance request tracker** (`fastapi-crud`): Shares the "submit request → track to resolution" shape; this plan reuses the submitter/approver flow and status model but adds a mandatory decision note, a fixed-list tool field, and a Member/Approver/Viewer role switcher instead of plain status edits.

## Scope
1. **Submit a loan request** — As a Member, I want to submit a request for a tool so an approver can decide on it.
   - Given I am in the Member role, When I submit name, tool (from the fixed list), start date, end date and reason, Then the request is created with status `Pending` and appears in the list.
   - Given I am in the Member role, When I omit a required field or choose a tool not on the fixed list, Then the request is rejected with a validation error and is not created.
   - Given I am in the Viewer or Approver role, When I view the app, Then I cannot access the submit form action.

2. **Approve or reject a request** — As an Approver, I want to decide on a pending request with a note so the reason is recorded.
   - Given I am in the Approver role viewing a `Pending` request, When I choose Approve or Reject and provide a note, Then the request status changes accordingly.
   - Given I am an Approver, When I try to decide without a note, Then the action is rejected and the status is unchanged.
   - Given a request is already `Approved` or `Rejected`, When an Approver views it, Then no further decision action is offered.

3. **Status list** — As any role, I want to see all requests and their current status.
   - Given any role, When I open the list page, Then I see every request with member name, tool, dates and current status (`Pending`/`Approved`/`Rejected`).

4. **Status history** — As any role, I want to see the decision history of a request.
   - Given any role viewing a request's detail, When history exists, Then each entry shows status, note, deciding role and timestamp in chronological order.

5. **Role switcher (no login)** — As a user, I want to switch between Member, Approver and Viewer without logging in.
   - Given I pick a role in the switcher, When the page reloads, Then only the actions allowed for that role are available (Member can submit, Approver can decide, Viewer is read-only).

## Out of scope
- Real login or authentication.
- Email or SMS notifications.
- A `Returned` status or any return workflow.
- Inventory or availability tracking of tools.
- Collecting contact details or other personal data.
- Free-text tool names (tools come from a fixed list only).

## Data model
Firestore collections:

**requests**
| Field | Type |
|---|---|
| `id` | string (doc id) |
| `member_name` | string |
| `tool` | string (must match a value in the fixed tools list) |
| `start_date` | string (ISO date, YYYY-MM-DD) |
| `end_date` | string (ISO date, YYYY-MM-DD) |
| `reason` | string |
| `status` | string enum: `Pending` \| `Approved` \| `Rejected` |
| `created_at` | timestamp |
| `updated_at` | timestamp |

**requests/{id}/history** (subcollection of status history entries)
| Field | Type |
|---|---|
| `status` | string enum: `Pending` \| `Approved` \| `Rejected` |
| `note` | string (required for Approve/Reject; may be "Submitted" on create) |
| `role` | string enum: `Member` \| `Approver` |
| `timestamp` | timestamp |

**Tool** — fixed list defined in code as a constant (e.g. `TOOLS = ["3D Printer", "Laser Cutter", "CNC Router", "Soldering Station", "Sewing Machine"]`), not a Firestore collection. The form and validation reference this list.

## Pages and endpoints
| Path | Purpose | Who uses it |
|---|---|---|
| `GET /` | List all requests with current status; shows role switcher and POC banner | All roles |
| `GET /requests/new` | Render the submit form (fixed tool dropdown) | Member |
| `POST /requests` | Create a request as `Pending`; writes first history entry | Member |
| `GET /requests/{id}` | Request detail with full status history | All roles |
| `POST /requests/{id}/decision` | Apply Approve/Reject with required note; append history | Approver |
| `POST /role` (or `?role=` query) | Set the active role (Member/Approver/Viewer) with no login | All roles |
| `GET /health` | Health check (unchanged from template) | Platform |

Role is carried via a simple cookie or query parameter set by the switcher — no credentials.

## Test plan
**Automated tests (builder must add):**
- Unit: tool validation rejects values not in the fixed `TOOLS` list.
- Unit: decision without a note raises a validation error and leaves status unchanged.
- Unit: a successful decision writes a history entry with status, note, role and timestamp.
- HTTP: `POST /requests` with valid payload returns success and the request is `Pending`.
- HTTP: `POST /requests/{id}/decision` as Approver with a note transitions status; a second decision on a non-`Pending` request is refused.
- HTTP: role gating — submit action blocked for Viewer/Approver; decision action blocked for Member/Viewer.
- HTTP: `GET /health` still returns 200 (template unchanged).

**Manual UAT checklist (staging):**
1. POC banner is visible on list, new, and detail pages.
2. As Member, submit a request with each required field; confirm it shows as `Pending`.
3. Try submitting with a missing field — confirm rejection.
4. Switch to Viewer — confirm no submit or decide actions appear.
5. Switch to Approver — approve one request with a note; reject another with a note.
6. Confirm statuses update in the list.
7. Open each request detail — confirm history shows the submit entry plus each decision with note, role and timestamp.
8. Confirm an already-decided request offers no further decision action.

## Risks and guardrails
- **No authentication (template rule):** roles are a switcher only; do not add login, sessions with credentials, or user accounts. Anyone can switch roles — acceptable for a POC.
- **No outbound HTTP, email, or notifications from the server** — decisions are recorded in Firestore only.
- **Fixed tool list** prevents free-text injection and keeps data clean; validate server-side, not just in the dropdown.
- **Required decision note** must be enforced server-side so history is always meaningful.
- **No personal data** beyond a display name — do not add contact fields.
- **Keep template banner, `/health` endpoint, Dockerfile and CI files unchanged.**
- Status transitions must only apply to `Pending` requests to avoid overwriting completed decisions.

## Builder instructions
1. Use the existing `form-workflow` FastAPI template. Do not modify the POC banner, `/health` endpoint, `Dockerfile`, or CI workflow files.
2. In the app config/constants module, add the fixed `TOOLS` list and the `Status` (`Pending`/`Approved`/`Rejected`) and `Role` (`Member`/`Approver`/`Viewer`) enums.
3. Define Pydantic models for the request payload (`member_name`, `tool`, `start_date`, `end_date`, `reason`) with server-side validation that `tool` is in `TOOLS` and dates are valid.
4. Add Firestore access in the data/service layer: create request (status `Pending`, write initial history entry `role=Member`, note `"Submitted"`), list requests, get request with its `history` subcollection, and apply a decision (update status + `updated_at`, append a history entry).
5. Implement the role switcher: a small form/control in the shared template that sets the active role via cookie or query param; read it in a dependency and expose it to templates.
6. Add route handlers:
   - `GET /` — list with role switcher.
   - `GET /requests/new` and `POST /requests` — gated to Member.
   - `GET /requests/{id}` — detail with history for all roles.
   - `POST /requests/{id}/decision` — gated to Approver, require non-empty note, only act on `Pending`.
7. Add server-side role gating in a shared dependency so disallowed actions return 403 (not just hidden in the UI).
8. Update templates: request list, new-request form (tool dropdown from `TOOLS`), and request detail with ordered history table. Keep the POC banner include on every page.
9. Add the automated tests listed in the Test plan under the template's existing tests directory.
10. Run the test suite locally and confirm `/health` still returns 200 before handing off.
