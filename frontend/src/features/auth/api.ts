import { useMutation } from '@tanstack/react-query'

import { api } from '@/lib/api-client'
import { queryClient } from '@/lib/query-client'
import { useAuthStore } from '@/stores/auth-store'
import { isMfaChallenge, type AuthResponse, type MessageResponse, type MfaChallengeResponse, type User } from '@/types/api'

export interface LoginInput {
  email: string
  password: string
}

export interface RegisterInput {
  company_name: string
  full_name: string
  email: string
  password: string
  company_size?: string | null
  timezone?: string
}

export interface ChangePasswordInput {
  current_password: string
  new_password: string
}

export const authApi = {
  login: (input: LoginInput) => api.post<AuthResponse | MfaChallengeResponse>('/auth/login', input, { auth: false }),
  verifyMfa: (input: { challenge: string; code: string }) => api.post<AuthResponse>('/auth/mfa/verify', input, { auth: false }),
  register: (input: RegisterInput) => api.post<AuthResponse>('/auth/register', input, { auth: false }),
  logout: () => api.post<void>('/auth/logout', undefined, { auth: false }),
  forgotPassword: (email: string) => api.post<MessageResponse>('/auth/forgot-password', { email }, { auth: false }),
  resetPassword: (token: string, password: string) =>
    api.post<MessageResponse>('/auth/reset-password', { token, password }, { auth: false }),
  verifyEmail: (token: string) => api.post<MessageResponse>('/auth/verify-email', { token }, { auth: false }),
  resendVerification: () => api.post<MessageResponse>('/auth/resend-verification'),
  changePassword: (input: ChangePasswordInput) => api.post<AuthResponse>('/auth/change-password', input),
  updateProfile: (input: { full_name: string }) => api.patch<User>('/users/me', input),
}

/** Password step. Resolves to a challenge (second step needed) or signs in directly. */
export function useLogin() {
  const setSession = useAuthStore((s) => s.setSession)
  return useMutation({
    mutationFn: authApi.login,
    onSuccess: (result) => {
      if (!isMfaChallenge(result)) setSession(result)
    },
  })
}

export function useVerifyMfa() {
  const setSession = useAuthStore((s) => s.setSession)
  return useMutation({ mutationFn: authApi.verifyMfa, onSuccess: setSession })
}

export function useRegister() {
  const setSession = useAuthStore((s) => s.setSession)
  return useMutation({ mutationFn: authApi.register, onSuccess: setSession })
}

export function useLogout() {
  const clearSession = useAuthStore((s) => s.clearSession)
  return useMutation({
    mutationFn: authApi.logout,
    onSettled: () => {
      // Sign out locally even if the network call fails.
      clearSession()
      queryClient.clear()
    },
  })
}

export function useForgotPassword() {
  return useMutation({ mutationFn: authApi.forgotPassword })
}

export function useResetPassword() {
  return useMutation({
    mutationFn: ({ token, password }: { token: string; password: string }) => authApi.resetPassword(token, password),
  })
}

export function useResendVerification() {
  return useMutation({ mutationFn: authApi.resendVerification })
}

export function useChangePassword() {
  const setSession = useAuthStore((s) => s.setSession)
  return useMutation({ mutationFn: authApi.changePassword, onSuccess: setSession })
}

export function useUpdateProfile() {
  const updateSession = useAuthStore((s) => s.updateSession)
  return useMutation({ mutationFn: authApi.updateProfile, onSuccess: (user) => updateSession({ user }) })
}
