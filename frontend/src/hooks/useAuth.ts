import { useCallback, useEffect, useState } from 'react';
import type { AuthResult, AuthSession, AuthUser } from '../types/auth';

/**
 * Auth hook.
 *
 * No external identity provider is configured, so the app runs as a single
 * local user. The sign-in/sign-up surface is retained so the existing screens
 * keep compiling and behaving as they already did with auth disabled; the
 * calls resolve immediately against the local user rather than a remote one.
 */

export const LOCAL_USER: AuthUser = {
  id: '00000000-0000-0000-0000-000000000000',
  email: 'dev@localhost',
  app_metadata: {},
  user_metadata: {},
  aud: 'authenticated',
  created_at: new Date(0).toISOString(),
};

const ok = (user: AuthUser | null = LOCAL_USER): AuthResult => ({
  data: { user, session: null },
  error: null,
});

export function useAuth() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [session] = useState<AuthSession | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setUser(LOCAL_USER);
    setLoading(false);
  }, []);

  const signUp = useCallback(async (_email: string, _password: string) => {
    setUser(LOCAL_USER);
    return ok();
  }, []);

  const signIn = useCallback(async (_email: string, _password: string) => {
    setUser(LOCAL_USER);
    return ok();
  }, []);

  const signInWithMagicLink = useCallback(async (_email: string) => {
    setUser(LOCAL_USER);
    return ok();
  }, []);

  const signOut = useCallback(async () => {
    setUser(null);
  }, []);

  const resendConfirmationEmail = useCallback(
    async (_email: string) => ok(null),
    []
  );

  /**
   * Metadata is kept in component state only. Durable profile fields belong to
   * the player profile, which the API already persists.
   */
  const updateUserMetadata = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    async (metadata: Record<string, any>) => {
      setUser((current) =>
        current
          ? {
              ...current,
              user_metadata: { ...current.user_metadata, ...metadata },
            }
          : current
      );
      return ok();
    },
    []
  );

  return {
    user,
    session,
    loading,
    signUp,
    signIn,
    signInWithMagicLink,
    signOut,
    resendConfirmationEmail,
    updateUserMetadata,
  };
}
