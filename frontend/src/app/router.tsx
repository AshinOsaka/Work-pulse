import { lazy, Suspense } from 'react'
import { createBrowserRouter, Navigate, Outlet, useParams } from 'react-router'

import { AppShell } from '@/components/layout/app-shell'
import { FullPageLoader } from '@/components/common/full-page-loader'
import { RedirectIfAuthenticated, RequireAuth, RequirePermission, RequireSection } from '@/features/auth/guards'
import { AcceptInvitePage } from '@/features/auth/pages/accept-invite-page'
import { LoginPage } from '@/features/auth/pages/login-page'
import { ForgotPasswordPage, ResetPasswordPage } from '@/features/auth/pages/password-pages'
import { RegisterPage } from '@/features/auth/pages/register-page'
import { VerifyEmailPage } from '@/features/auth/pages/verify-email-page'
import { ContentErrorPage, NotFoundPage, RouteErrorPage } from '@/features/errors/error-pages'

// Application pages are code-split; the auth flow stays in the main bundle.
const DashboardPage = lazy(() => import('@/features/dashboard/dashboard-page'))
const SecurityPage = lazy(() => import('@/features/security/security-page'))
const ActivityPage = lazy(() => import('@/features/activity/activity-page'))
const ProductivityLayout = lazy(() => import('@/features/productivity/pages').then((m) => ({ default: m.ProductivityLayout })))
const ProductivityOverviewPage = lazy(() =>
  import('@/features/productivity/pages').then((m) => ({ default: m.ProductivityOverviewPage })),
)
const ProductivityEmployeePage = lazy(() =>
  import('@/features/productivity/pages').then((m) => ({ default: m.ProductivityEmployeePage })),
)
const ProductivityGroupsPage = lazy(() => import('@/features/productivity/pages').then((m) => ({ default: m.ProductivityGroupsPage })))
const ProductivityTrendsPage = lazy(() => import('@/features/productivity/pages').then((m) => ({ default: m.ProductivityTrendsPage })))
const ProductivityRulesPage = lazy(() => import('@/features/productivity/rules-page'))
const ProductivityBreakdownPage = lazy(() => import('@/features/productivity/productivity-breakdown-page'))
const ReportsPage = lazy(() => import('@/features/reports/reports-page'))
const AssistantPage = lazy(() => import('@/features/assistant/assistant-page'))
const PrivacyPage = lazy(() => import('@/features/privacy/privacy-page'))
const NotificationsPage = lazy(() => import('@/features/notifications/notifications-page'))
const TutorialsPage = lazy(() => import('@/features/tutorials/tutorials-page'))
const WorkLayout = lazy(() => import('@/features/work/pages/layout'))
const ProjectsPage = lazy(() => import('@/features/work/pages/projects-page'))
const ProjectPage = lazy(() => import('@/features/work/pages/project-page'))
const MyWorkPage = lazy(() => import('@/features/work/pages/my-work-page'))
const TeamWorkPage = lazy(() => import('@/features/work/pages/team-page'))
const LivePage = lazy(() => import('@/features/live/live-page'))
const LiveViewerPage = lazy(() => import('@/features/live/live-viewer-page'))
const ScreenshotsPage = lazy(() => import('@/features/screenshots/screenshots-page'))

const SettingsLayout = lazy(() => import('@/features/settings/settings-page'))
const ProfileSettings = lazy(() => import('@/features/settings/settings-page').then((m) => ({ default: m.ProfileSettings })))
const WorkspaceSettings = lazy(() =>
  import('@/features/settings/settings-page').then((m) => ({ default: m.WorkspaceSettings })),
)
const AppearanceSettings = lazy(() =>
  import('@/features/settings/settings-page').then((m) => ({ default: m.AppearanceSettings })),
)
const CustomerSystemsSettings = lazy(() =>
  import('@/features/settings/settings-page').then((m) => ({ default: m.CustomerSystemsSettings })),
)
const DesktopAgentSettings = lazy(() =>
  import('@/features/settings/settings-page').then((m) => ({ default: m.DesktopAgentSettings })),
)
const RolesPage = lazy(() => import('@/features/settings/roles-page'))
const AccessPage = lazy(() => import('@/features/settings/access-page'))

const PeopleLayout = lazy(() => import('@/features/people/pages/people-layout'))
const PeopleOverviewPage = lazy(() => import('@/features/people/pages/people-overview-page'))
const EmployeesPage = lazy(() => import('@/features/people/pages/employees-page'))
const EmployeeProfilePage = lazy(() => import('@/features/people/pages/employee-profile-page'))
const DepartmentsPage = lazy(() =>
  import('@/features/people/pages/structure-pages').then((m) => ({ default: m.DepartmentsPage })),
)
const TeamsPage = lazy(() => import('@/features/people/pages/structure-pages').then((m) => ({ default: m.TeamsPage })))
const JobRolesPage = lazy(() => import('@/features/people/pages/job-roles-page'))
const AttendancePage = lazy(() => import('@/features/attendance/attendance-page'))

function LiveTrackingRedirect() {
  const { sessionId } = useParams()
  return <Navigate to={`/live/${sessionId ?? ''}`} replace />
}

export const router = createBrowserRouter([
  {
    element: <Outlet />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        element: <RedirectIfAuthenticated />,
        children: [
          { path: 'login', element: <LoginPage /> },
          { path: 'register', element: <RegisterPage /> },
          { path: 'forgot-password', element: <ForgotPasswordPage /> },
        ],
      },
      // Reachable from e-mail links whether or not the visitor is signed in.
      { path: 'reset-password', element: <ResetPasswordPage /> },
      { path: 'verify-email', element: <VerifyEmailPage /> },
      { path: 'accept-invite', element: <AcceptInvitePage /> },
      {
        element: <RequireAuth />,
        children: [
          // /live-tracking is an alias of /live (both URLs work; /live is canonical).
          { path: 'live-tracking', element: <Navigate to="/live" replace /> },
          { path: 'live-tracking/:sessionId', element: <LiveTrackingRedirect /> },
          // The live viewer uses the whole window (no sidebar); it is still behind authentication.
          {
            path: 'live/:sessionId',
            element: (
              <Suspense fallback={<FullPageLoader label="Opening live view…" />}>
                <RequirePermission permission="LIVE_STREAM_VIEW">
                  <LiveViewerPage />
                </RequirePermission>
              </Suspense>
            ),
          },
          {
            element: <AppShell />,
            children: [
              {
                // Errors inside a page keep the sidebar and top bar, so people can navigate away.
                errorElement: <ContentErrorPage />,
                children: [
                  { index: true, element: <Navigate to="/dashboard" replace /> },
                  { path: 'dashboard', element: <DashboardPage /> },
                  {
                    path: 'people',
                    children: [
                      {
                        element: (
                          <RequireSection section="people">
                            <PeopleLayout />
                          </RequireSection>
                        ),
                        children: [
                          { index: true, element: <PeopleOverviewPage /> },
                          { path: 'employees', element: <EmployeesPage /> },
                          { path: 'departments', element: <DepartmentsPage /> },
                          { path: 'teams', element: <TeamsPage /> },
                          { path: 'job-roles', element: <JobRolesPage /> },
                        ],
                      },
                      // Profiles sit outside the tabbed layout: employees may open their own.
                      { path: 'employees/:id', element: <EmployeeProfilePage /> },
                    ],
                  },
                  {
                    path: 'settings',
                    element: <SettingsLayout />,
                    children: [
                      { index: true, element: <Navigate to="profile" replace /> },
                      { path: 'profile', element: <ProfileSettings /> },
                      { path: 'workspace', element: <WorkspaceSettings /> },
                      { path: 'agent', element: <DesktopAgentSettings /> },
                      { path: 'customer-systems', element: <CustomerSystemsSettings /> },
                      { path: 'appearance', element: <AppearanceSettings /> },
                      { path: 'privacy', element: <PrivacyPage /> },
                      { path: 'roles', element: <RolesPage /> },
                      { path: 'access', element: <AccessPage /> },
                    ],
                  },
                  { path: 'security', element: <SecurityPage /> },
                  { path: 'help', element: <TutorialsPage /> },
                  { path: 'activity', element: <RequireSection section="activity"><ActivityPage /></RequireSection> },
                  { path: 'attendance', element: <RequireSection section="attendance"><AttendancePage /></RequireSection> },
                  { path: 'screenshots', element: <RequireSection section="screenshots"><ScreenshotsPage /></RequireSection> },
                  { path: 'live', element: <RequireSection section="live"><LivePage /></RequireSection> },
                  {
                    path: 'projects',
                    element: (
                      <RequireSection section="projects">
                        <WorkLayout />
                      </RequireSection>
                    ),
                    children: [
                      { index: true, element: <ProjectsPage /> },
                      { path: 'my-work', element: <MyWorkPage /> },
                      { path: 'team', element: <TeamWorkPage /> },
                      { path: ':projectId', element: <ProjectPage /> },
                    ],
                  },
                  {
                    path: 'productivity',
                    element: (
                      <RequireSection section="productivity">
                        <ProductivityLayout />
                      </RequireSection>
                    ),
                    children: [
                      { index: true, element: <ProductivityOverviewPage /> },
                      { path: 'breakdown', element: <ProductivityBreakdownPage /> },
                      { path: 'departments', element: <ProductivityGroupsPage /> },
                      { path: 'trends', element: <ProductivityTrendsPage /> },
                      { path: 'rules', element: <ProductivityRulesPage /> },
                      { path: 'employees/:employeeId', element: <ProductivityEmployeePage /> },
                    ],
                  },
                  { path: 'reports', element: <RequireSection section="reports"><ReportsPage /></RequireSection> },
                  { path: 'alerts', element: <RequireSection section="alerts"><NotificationsPage /></RequireSection> },
                  { path: 'privacy', element: <Navigate to="/settings/privacy" replace /> },
                  { path: 'assistant', element: <RequireSection section="assistant"><AssistantPage /></RequireSection> },
                ],
              },
            ],
          },
        ],
      },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
