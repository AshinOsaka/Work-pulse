import type { ReactNode } from 'react'
import { Link } from 'react-router'

/**
 * A deliberately small Markdown subset for assistant answers: paragraphs, headings, lists, simple tables, bold,
 * italic, code and links. It builds React elements (never raw HTML), and only same-origin paths become links — the
 * assistant links to WorkPulse pages it got from its tools, nothing else.
 */

const INLINE = /(`[^`\n]+`)|(\*\*[^*\n]+?\*\*)|(\[[^\]\n]+\]\([^)\s]+\))|(\*[^*\s][^*\n]*?\*)|(_[^_\s][^_\n]*?_)/g

export function isInternal(href: string): boolean {
  return href.startsWith('/') && !href.startsWith('//')
}

function inline(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = []
  let last = 0
  let i = 0
  for (const match of text.matchAll(INLINE)) {
    const [token] = match
    const at = match.index
    if (at > last) out.push(text.slice(last, at))
    const k = `${key}-${i++}`
    if (token.startsWith('`')) {
      out.push(
        <code key={k} className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">
          {token.slice(1, -1)}
        </code>,
      )
    } else if (token.startsWith('**')) {
      out.push(
        <strong key={k} className="font-semibold text-foreground">
          {inline(token.slice(2, -2), k)}
        </strong>,
      )
    } else if (token.startsWith('[')) {
      const split = token.indexOf('](')
      const label = token.slice(1, split)
      const href = token.slice(split + 2, -1)
      out.push(
        isInternal(href) ? (
          <Link key={k} to={href} className="font-medium text-primary underline-offset-2 hover:underline">
            {inline(label, k)}
          </Link>
        ) : (
          <span key={k}>{inline(label, k)}</span>
        ),
      )
    } else {
      out.push(<em key={k}>{inline(token.slice(1, -1), k)}</em>)
    }
    last = at + token.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

const cells = (row: string) =>
  row
    .trim()
    .replace(/^\||\|$/g, '')
    .split('|')
    .map((c) => c.trim())

export function Markdown({ text }: { text: string }) {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const blocks: ReactNode[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    const key = `b${i}`
    if (!line.trim()) {
      i++
      continue
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line)
    if (heading) {
      blocks.push(
        <p key={key} className="mt-1 font-semibold text-foreground">
          {inline(heading[2], key)}
        </p>,
      )
      i++
      continue
    }
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      const head = cells(line)
      const body: string[][] = []
      i += 2
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) body.push(cells(lines[i++]))
      blocks.push(
        <div key={key} className="relative overflow-x-auto rounded-md border">
          <table className="w-full text-[13px]">
            <thead className="bg-muted/50 text-left text-muted-foreground">
              <tr>
                {head.map((h, c) => (
                  <th key={c} scope="col" className="px-3 py-1.5 font-medium whitespace-nowrap">
                    {inline(h, `${key}h${c}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {body.map((row, r) => (
                <tr key={r} className="border-t">
                  {row.map((cell, c) => (
                    <td key={c} className="px-3 py-1.5 tabular">
                      {inline(cell, `${key}r${r}c${c}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }
    const listItem = /^\s*([-*•]|\d+[.)])\s+(.*)$/
    if (listItem.test(line)) {
      const ordered = /^\s*\d/.test(line)
      const items: string[] = []
      while (i < lines.length && listItem.test(lines[i])) items.push(listItem.exec(lines[i++])![2])
      const List = ordered ? 'ol' : 'ul'
      blocks.push(
        <List key={key} className={ordered ? 'list-decimal space-y-1 pl-5' : 'list-disc space-y-1 pl-5 marker:text-muted-foreground'}>
          {items.map((item, n) => (
            <li key={n}>{inline(item, `${key}i${n}`)}</li>
          ))}
        </List>,
      )
      continue
    }
    const paragraph: string[] = []
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|\s*([-*•]|\d+[.)])\s|\s*\|)/.test(lines[i])) paragraph.push(lines[i++])
    if (!paragraph.length) paragraph.push(lines[i++])
    blocks.push(
      <p key={key}>
        {paragraph.flatMap((p, n) => (n ? [<br key={`br${n}`} />, ...inline(p, `${key}p${n}`)] : inline(p, `${key}p${n}`)))}
      </p>,
    )
  }
  return <div className="space-y-2.5 text-sm leading-relaxed text-foreground/90">{blocks}</div>
}
