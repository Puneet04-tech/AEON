"""JSON-schema validators for the collections the blueprint marks as strict.

`apply_validators` is best-effort: some managed clusters (and mongomock) do not
expose collection options, so failures are logged instead of raising.
"""
from typing import Dict, Any

import structlog

logger = structlog.get_logger()

ACCOUNTS = [
    "treasury_float",
    "agent_available",
    "agent_escrow",
    "agent_bond",
    "platform_fees",
    "loan_receivable",
    "loan_payable",
    "payout_in_flight",
    "dust",
]

VALIDATORS: Dict[str, Dict[str, Any]] = {
    "ledger_entries": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["id", "txn_id", "account", "amount_micro", "currency", "idem_key", "posted_at"],
            "properties": {
                "id": {"bsonType": "string"},
                "txn_id": {"bsonType": "string"},
                "account": {"enum": ACCOUNTS},
                "agent_id": {"bsonType": ["string", "null"]},
                "amount_micro": {"bsonType": ["int", "long"]},
                "currency": {"enum": ["USD"]},
                "idem_key": {"bsonType": "string", "minLength": 8},
                "posted_at": {"bsonType": "date"},
            },
        }
    },
    "wallets": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["agent_id", "available_micro", "escrow_micro", "bond_micro", "currency"],
            "properties": {
                "agent_id": {"bsonType": "string"},
                "available_micro": {"bsonType": ["int", "long"], "minimum": 0},
                "escrow_micro": {"bsonType": ["int", "long"], "minimum": 0},
                "bond_micro": {"bsonType": ["int", "long"], "minimum": 0},
                "dust_micro": {"bsonType": ["int", "long"]},
                "currency": {"enum": ["USD"]},
                "version": {"bsonType": ["int", "long"]},
            },
        }
    },
    "trades": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["id", "buyer_id", "seller_id", "state", "agreed", "created_at"],
            "properties": {
                "id": {"bsonType": "string"},
                "buyer_id": {"bsonType": "string"},
                "seller_id": {"bsonType": "string"},
                "state": {"bsonType": "string"},
                "agreed": {
                    "bsonType": "object",
                    "required": ["price_micro", "quantity"],
                    "properties": {
                        "price_micro": {"bsonType": ["int", "long"], "minimum": 1},
                        "quantity": {"bsonType": ["int", "long"], "minimum": 1},
                    },
                },
                "created_at": {"bsonType": "date"},
            },
        }
    },
    "settlements": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["id", "state", "sender_batch_id", "totals"],
            "properties": {
                "id": {"bsonType": "string"},
                "state": {"enum": ["DRAFT", "AWAITING_APPROVAL", "OPEN", "SUBMITTED", "SUCCEEDED", "PARTIAL", "FAILED"]},
                "sender_batch_id": {"bsonType": "string"},
                "totals": {
                    "bsonType": "object",
                    "required": ["items", "amount_micro"],
                    "properties": {
                        "items": {"bsonType": ["int", "long"]},
                        "amount_micro": {"bsonType": ["int", "long"]},
                    },
                },
            },
        }
    },
    "payout_items": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["id", "settlement_id", "agent_id", "amount_micro", "state"],
            "properties": {
                "id": {"bsonType": "string"},
                "settlement_id": {"bsonType": "string"},
                "agent_id": {"bsonType": "string"},
                "amount_micro": {"bsonType": ["int", "long"], "minimum": 1},
                "state": {"enum": ["PENDING", "SUBMITTED", "SUCCESS", "FAILED", "RETURNED", "CANCELLED"]},
            },
        }
    },
}


async def apply_validators(db) -> int:
    applied = 0
    existing = set(await db.list_collection_names())
    for name, validator in VALIDATORS.items():
        if name not in existing:
            try:
                await db.create_collection(name, validator=validator,
                                           validationLevel="strict",
                                           validationAction="error")
                applied += 1
                continue
            except Exception as exc:  # pragma: no cover - cluster dependent
                logger.warning("validator_create_failed", collection=name, error=str(exc))
                continue
        try:
            await db.command({
                "collMod": name,
                "validator": validator,
                "validationLevel": "strict",
                "validationAction": "error",
            })
            applied += 1
        except Exception as exc:  # pragma: no cover - cluster dependent
            logger.warning("validator_mod_failed", collection=name, error=str(exc))
    logger.info("validators_ready", count=applied)
    return applied
