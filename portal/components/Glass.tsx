import type { HTMLAttributes } from 'react'

type Props = HTMLAttributes<HTMLDivElement> & { strong?: boolean }

/** Thin semantic wrapper over the `.glass`/`.glass-strong` CSS classes
 * (globals.css) — the signature frosted-glass surface used everywhere. */
export function Glass({ strong, className = '', ...rest }: Props) {
  return <div className={`${strong ? 'glass-strong' : 'glass'} ${className}`} {...rest} />
}
