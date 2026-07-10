type Props = {
  n: number
  onClick: () => void
}

export function CitationChip({ n, onClick }: Props) {
  return (
    <button
      onClick={onClick}
      className="mx-0.5 cursor-pointer rounded bg-brand/15 px-1.5 align-super text-xs font-semibold leading-none text-brand transition-colors hover:bg-brand/30"
      aria-label={`View source ${n}`}
    >
      {n}
    </button>
  )
}
