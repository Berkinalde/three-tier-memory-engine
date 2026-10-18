import argparse
import json
import sys
from .models import Scope, MemoryInput, MemoryError, encode, require
from .repository import Repository
from .service import MemoryService


def main():
    parser = argparse.ArgumentParser(description="Three-tier memory JSON CLI")
    parser.add_argument("--db", default="memory.db")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--user", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--idempotency-key")
    create.add_argument("--authoritative", action="store_true")
    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--session-id")
    search.add_argument("--task-id")
    search.add_argument("--tier", action="append")
    search.add_argument("--top-k", type=int, default=10)
    for name in ("get", "delete", "update"):
        cmd = sub.add_parser(name)
        cmd.add_argument("id")
        if name == "update":
            cmd.add_argument("--version", type=int, required=True)
            cmd.add_argument("--authoritative", action="store_true")
    sub.add_parser("expire")
    sub.add_parser("delete-user")
    args = parser.parse_args()
    try:
        service = MemoryService(Repository(args.db))
        scope = Scope(args.tenant, args.user)
        if args.command in ("create", "update"):
            raw = sys.stdin.buffer.read(65537)
            require(len(raw) <= 65536, "body_too_large")
            data = json.loads(raw)
            authority = "user" if args.authoritative else "untrusted"
        if args.command == "create":
            result = service.create(
                scope, MemoryInput.from_dict(data), idempotency_key=args.idempotency_key, authority=authority
            )
        elif args.command == "search":
            result = service.retrieve(
                scope,
                args.query,
                session_id=args.session_id,
                task_id=args.task_id,
                top_k=args.top_k,
                tier_filters=args.tier,
            )
        elif args.command == "get":
            result = service.get(scope, args.id)
        elif args.command == "update":
            result = service.update(
                scope, args.id, expected_version=args.version, changes=data, authority=authority
            )
        elif args.command == "delete":
            result = {"deleted": service.delete_memory(scope, args.id)}
        elif args.command == "delete-user":
            result = {"deleted": service.delete_user_data(scope)}
        else:
            result = {"deleted": service.expire(scope)}
        print(encode(result))
        return 0
    except (MemoryError, ValueError, UnicodeError, RecursionError) as exc:
        print(encode({"error": getattr(exc, "code", "invalid_json")}), file=sys.stderr)
        return 1
