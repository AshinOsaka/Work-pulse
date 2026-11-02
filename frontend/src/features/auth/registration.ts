/**
 * Whether public self-service workspace registration is offered in this build.
 * A single-company deployment sets VITE_ALLOW_REGISTRATION=false, which hides the
 * "Create a workspace" link and blocks the /register page. The backend enforces the
 * same with ALLOW_REGISTRATION (so a direct API call is refused regardless).
 */
export const registrationEnabled = import.meta.env.VITE_ALLOW_REGISTRATION !== 'false'
