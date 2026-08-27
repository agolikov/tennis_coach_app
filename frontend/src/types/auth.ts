/**
 * Local auth types.
 *
 * No external identity provider is wired up. These types keep the shape the
 * components already consume so the auth surface stays typed, while the app
 * runs as a single local user.
 */

export interface AuthUser {
  id: string;
  email: string;
  // Loosely typed, matching how the screens read optional profile fields
  // such as display_name off the user.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  app_metadata: Record<string, any>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  user_metadata: Record<string, any>;
  aud: string;
  created_at: string;
}

export interface AuthSession {
  access_token: string;
  user: AuthUser;
}

export type AuthError = { message: string } | null;

export interface AuthResult {
  data: { user: AuthUser | null; session: AuthSession | null } | null;
  error: AuthError;
}
