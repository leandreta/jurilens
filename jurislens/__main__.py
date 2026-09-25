"""CLI: python -m jurislens {extract,bench,synth,redact}"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import bench, hybrid, redact, synth


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="jurislens", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract", help="extrai dados de um .txt (ou stdin)")
    e.add_argument("file", nargs="?", help="arquivo de texto; omita para ler do stdin")
    e.add_argument("--no-llm", action="store_true", help="usa só regras + validação")
    e.add_argument("--redact", action="store_true", help="mascara CPF/CNPJ na saída (LGPD)")

    b = sub.add_parser("bench", help="roda o benchmark e atualiza README/results")
    b.add_argument("-n", type=int, default=90)
    b.add_argument("--llm-sample", type=int, default=30)
    b.add_argument("--dry-run", action="store_true", help="só imprime, não grava arquivos")

    s = sub.add_parser("synth", help="gera processos sintéticos com gabarito")
    s.add_argument("-n", type=int, default=90)
    s.add_argument("--seed", type=int, default=2026)
    s.add_argument("-o", "--out", default=str(bench.DATASET))

    args = p.parse_args(argv)

    if args.cmd == "extract":
        text = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
        r = hybrid.extract(text, use_llm=False if args.no_llm else None)
        data = redact.mask_output(r.data) if args.redact else r.data
        print(json.dumps({"dados": data, "origem": r.source, "descartados_pela_validacao": r.rejected,
                          "custo_usd": round(r.cost_usd, 5)}, ensure_ascii=False, indent=2))
    elif args.cmd == "bench":
        report = bench.run(n=args.n, llm_sample=args.llm_sample)
        if not args.dry_run:
            bench.write(report)
        print(bench.markdown(report))
    elif args.cmd == "synth":
        cases = synth.generate(args.n, args.seed)
        synth.save(cases, Path(args.out))
        print(f"{len(cases)} processos sintéticos -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
