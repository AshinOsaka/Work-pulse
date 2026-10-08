/**
 * SAMPLE DATA — a fictional organisation used only in the dashboard's sample mode.
 * None of these people exist in any workspace; they are never mixed with real employees.
 */
import type { AlertSeverity, AlertType, AppCategory } from '@/features/dashboard/data/types'

export interface SampleTeam {
  id: string
  name: string
  /** Relative productivity offset so teams differ believably. */
  bias: number
}

export const SAMPLE_TEAMS: SampleTeam[] = [
  { id: 'sample-platform', name: 'Platform', bias: 4 },
  { id: 'sample-web', name: 'Web & Mobile', bias: 2 },
  { id: 'sample-sales', name: 'Sales', bias: -3 },
  { id: 'sample-success', name: 'Customer Success', bias: 0 },
  { id: 'sample-finance', name: 'Finance & Ops', bias: 1 },
]

export const SAMPLE_PEOPLE: { name: string; title: string; teamId: string }[] = [
  { name: 'Avery Collins', title: 'Staff Engineer', teamId: 'sample-platform' },
  { name: 'Mateo Rossi', title: 'Backend Engineer', teamId: 'sample-platform' },
  { name: 'Yuki Tanaka', title: 'Site Reliability Engineer', teamId: 'sample-platform' },
  { name: 'Nadia Haddad', title: 'Backend Engineer', teamId: 'sample-platform' },
  { name: 'Jonas Berg', title: 'Engineering Manager', teamId: 'sample-platform' },
  { name: 'Chloe Martin', title: 'Data Engineer', teamId: 'sample-platform' },
  { name: 'Ravi Menon', title: 'Platform Engineer', teamId: 'sample-platform' },
  { name: 'Isla Murphy', title: 'Frontend Engineer', teamId: 'sample-web' },
  { name: 'Kwame Asante', title: 'iOS Engineer', teamId: 'sample-web' },
  { name: 'Lena Fischer', title: 'Product Designer', teamId: 'sample-web' },
  { name: 'Diego Santos', title: 'Frontend Engineer', teamId: 'sample-web' },
  { name: 'Hana Kobayashi', title: 'Android Engineer', teamId: 'sample-web' },
  { name: 'Owen Price', title: 'QA Engineer', teamId: 'sample-web' },
  { name: 'Zara Ahmed', title: 'UX Researcher', teamId: 'sample-web' },
  { name: 'Lucas Moreau', title: 'Account Executive', teamId: 'sample-sales' },
  { name: 'Priyanka Iyer', title: 'Sales Development Rep', teamId: 'sample-sales' },
  { name: 'Ethan Walker', title: 'Account Executive', teamId: 'sample-sales' },
  { name: 'Sofia Novak', title: 'Sales Manager', teamId: 'sample-sales' },
  { name: 'Marcus Reid', title: 'Sales Development Rep', teamId: 'sample-sales' },
  { name: 'Amara Okeke', title: 'Solutions Consultant', teamId: 'sample-sales' },
  { name: 'Felix Wagner', title: 'Account Executive', teamId: 'sample-sales' },
  { name: 'Grace Lin', title: 'Support Specialist', teamId: 'sample-success' },
  { name: 'Tomás Herrera', title: 'Support Specialist', teamId: 'sample-success' },
  { name: 'Noor Khalil', title: 'Customer Success Manager', teamId: 'sample-success' },
  { name: 'Ben Carter', title: 'Onboarding Specialist', teamId: 'sample-success' },
  { name: 'Elif Demir', title: 'Support Lead', teamId: 'sample-success' },
  { name: 'Sam Oduya', title: 'Support Specialist', teamId: 'sample-success' },
  { name: 'Mia Johansson', title: 'Customer Success Manager', teamId: 'sample-success' },
  { name: 'Leo Fernández', title: 'Support Specialist', teamId: 'sample-success' },
  { name: 'Olivia Grant', title: 'Financial Analyst', teamId: 'sample-finance' },
  { name: 'Henrik Lund', title: 'Controller', teamId: 'sample-finance' },
  { name: 'Aisha Bello', title: 'Payroll Specialist', teamId: 'sample-finance' },
  { name: 'Daniel Kim', title: 'Operations Manager', teamId: 'sample-finance' },
  { name: 'Clara Weiss', title: 'Office Coordinator', teamId: 'sample-finance' },
]

export const SAMPLE_APPS: Record<string, { name: string; category: AppCategory }[]> = {
  'sample-platform': [
    { name: 'Visual Studio Code', category: 'productive' },
    { name: 'Terminal', category: 'productive' },
    { name: 'GitHub', category: 'productive' },
    { name: 'Grafana', category: 'productive' },
    { name: 'Slack', category: 'neutral' },
    { name: 'Zoom', category: 'neutral' },
  ],
  'sample-web': [
    { name: 'Figma', category: 'productive' },
    { name: 'Visual Studio Code', category: 'productive' },
    { name: 'Xcode', category: 'productive' },
    { name: 'Chrome · localhost', category: 'productive' },
    { name: 'Slack', category: 'neutral' },
    { name: 'YouTube', category: 'unproductive' },
  ],
  'sample-sales': [
    { name: 'Salesforce', category: 'productive' },
    { name: 'Gmail', category: 'neutral' },
    { name: 'LinkedIn Sales Navigator', category: 'productive' },
    { name: 'Zoom', category: 'neutral' },
    { name: 'Slack', category: 'neutral' },
    { name: 'Instagram', category: 'unproductive' },
  ],
  'sample-success': [
    { name: 'Zendesk', category: 'productive' },
    { name: 'Intercom', category: 'productive' },
    { name: 'Notion', category: 'productive' },
    { name: 'Slack', category: 'neutral' },
    { name: 'Gmail', category: 'neutral' },
  ],
  'sample-finance': [
    { name: 'Excel', category: 'productive' },
    { name: 'NetSuite', category: 'productive' },
    { name: 'Outlook', category: 'neutral' },
    { name: 'Teams', category: 'neutral' },
    { name: 'News site', category: 'unproductive' },
  ],
}

export const SAMPLE_TASKS: Record<string, string[]> = {
  'sample-platform': ['Migrate billing service to Postgres 17', 'Fix flaky CI pipeline', 'On-call: API latency spike', 'Rate limiter v2', 'Code review: auth refresh'],
  'sample-web': ['Checkout redesign', 'Dark mode polish', 'Push notification opt-in', 'Accessibility audit fixes', 'Release 4.12 QA'],
  'sample-sales': ['Q4 pipeline review', 'Enterprise demo: Contoso', 'Follow-up sequence: webinar leads', 'Renewal negotiation: Fabrikam'],
  'sample-success': ['Ticket queue: priority', 'Onboarding: Northwind Traders', 'Quarterly business review prep', 'Knowledge base refresh'],
  'sample-finance': ['Month-end close', 'Payroll run', 'Vendor reconciliation', 'Budget forecast FY27'],
}

export const SAMPLE_DEVICES: { name: string; os: 'windows' | 'macos' | 'linux' }[] = [
  { name: 'MacBook Pro 14"', os: 'macos' },
  { name: 'MacBook Air 13"', os: 'macos' },
  { name: 'ThinkPad X1 Carbon', os: 'windows' },
  { name: 'Dell XPS 15', os: 'windows' },
  { name: 'Surface Laptop 6', os: 'windows' },
  { name: 'Framework 13', os: 'linux' },
]

export const SAMPLE_ALERT_TYPES: { type: AlertType; severity: AlertSeverity; detail: (app: string) => string }[] = [
  { type: 'idle_time', severity: 'medium', detail: () => 'Idle for more than 45 minutes during working hours' },
  { type: 'unproductive_app', severity: 'low', detail: (app) => `More than 30 minutes on ${app}` },
  { type: 'overtime', severity: 'medium', detail: () => 'Worked over 10 hours today' },
  { type: 'agent_offline', severity: 'high', detail: () => 'Desktop agent stopped reporting during a scheduled shift' },
  { type: 'blocked_site', severity: 'critical', detail: () => 'Visited a site blocked by the security policy' },
]
