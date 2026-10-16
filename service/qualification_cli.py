"""Explicit offline qualification commands; no execution enablement option."""

from .qualification import (prepare_qualification, run_qualification, read_qualification_report,
                            create_qualification_handoff)


def add_commands(commands):
    prepare = commands.add_parser("qualification-prepare", help="Freeze offline evidence against an unstarted repair")
    prepare.add_argument("--output", required=True)
    prepare.add_argument("--repair-output", required=True)
    prepare.add_argument("--execution-deadline", type=float, required=True)
    prepare.add_argument("--review-deadline", type=float, required=True)
    for name in ("run", "report", "handoff"):
        command = commands.add_parser("qualification-" + name, help="Offline mock evidence; live gates pending; no execution authority")
        command.add_argument("--output", required=True)
        if name == "handoff":
            command.add_argument("--repair-output", required=True)


def execute(args):
    if args.command == "qualification-prepare":
        return prepare_qualification(args.output, args.repair_output,
                execution_deadline=args.execution_deadline, review_deadline=args.review_deadline)
    if args.command == "qualification-run":
        return run_qualification(args.output)
    if args.command == "qualification-report":
        return read_qualification_report(args.output)
    if args.command == "qualification-handoff":
        return create_qualification_handoff(args.output, args.repair_output)
    raise ValueError("unsupported qualification command")
