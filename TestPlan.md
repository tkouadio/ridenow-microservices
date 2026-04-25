# TestPlan.md — Flux nominal RideNow

## Prérequis

- Docker et Docker Compose installés
- Ports 8000–8004 disponibles sur la machine hôte

## Données de test (seed data)

| Entité | ID | Détails |
|--------|----|---------|
| Passager | 100 | Paul Passenger |
| Passager | 101 | Mia Passenger |
| Chauffeur | 1 | Alice Driver, zone A, disponible |
| Chauffeur | 2 | Bob Driver, zone B, **indisponible** |
| Chauffeur | 3 | Charlie Driver, zone A, disponible |
| Prix A→B | — | $15.00 |

---

## Démarrage du stack

```bash
docker compose up --build -d
```

Attendre ~5 secondes que tous les services démarrent.

---

## Étape 0 — Health checks

```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
curl http://localhost:8004/health
```

**Résultat attendu :** HTTP 200 avec `{"status": "ok"}` sur chaque service.

---

## Étape 1 — Créer une course (`POST /demo/request-ride`)

```bash
curl -s -X POST http://localhost:8000/demo/request-ride \
  -H "Content-Type: application/json" \
  -d '{"passenger_id": 100, "from_zone": "A", "to_zone": "B"}' | python3 -m json.tool
```

**Résultat attendu (HTTP 201) :**

```json
{
    "ride": {
        "status": "ASSIGNED",
        "payment_status": "AUTHORIZED",
        "amount": 15.0
    },
    "payment": {
        "status": "AUTHORIZED"
    }
}
```

**Vérification complémentaire — chauffeur réservé :**

```bash
curl -s http://localhost:8001/drivers/1 | python3 -m json.tool
```

Résultat attendu : `"available": false`

> Note : le champ `driver.available` dans la réponse du gateway affiche `true` car il reflète l'état *avant* la mise à jour de disponibilité. L'état réel est `false`, confirmé par la requête ci-dessus.

---

## Étape 2 — Accepter la course (`ASSIGNED → ACCEPTED`)

```bash
curl -s -X PATCH http://localhost:8000/demo/rides/1/status \
  -H "Content-Type: application/json" \
  -d '{"status": "ACCEPTED"}' | python3 -m json.tool
```

**Résultat attendu (HTTP 200) :** `"status": "ACCEPTED"`

---

## Étape 3 — Démarrer la course (`ACCEPTED → STARTED`)

```bash
curl -s -X PATCH http://localhost:8000/demo/rides/1/status \
  -H "Content-Type: application/json" \
  -d '{"status": "STARTED"}' | python3 -m json.tool
```

**Résultat attendu (HTTP 200) :** `"status": "STARTED"`

---

## Étape 4 — Compléter la course (`STARTED → COMPLETED`)

```bash
curl -s -X PATCH http://localhost:8000/demo/rides/1/status \
  -H "Content-Type: application/json" \
  -d '{"status": "COMPLETED"}' | python3 -m json.tool
```

**Résultat attendu (HTTP 200) :**

```json
{
    "ride": {
        "status": "COMPLETED",
        "payment_status": "CAPTURED"
    },
    "payment": {
        "status": "CAPTURED"
    },
    "driver_availability": {
        "available": true
    }
}
```

---

## Étape 5 — Projection finale (`GET /demo/rides/1`)

```bash
curl -s http://localhost:8000/demo/rides/1 | python3 -m json.tool
```

**Résultat attendu (HTTP 200) :**

```json
{
    "ride": {
        "status": "COMPLETED",
        "payment_status": "CAPTURED"
    },
    "driver": {
        "available": true
    },
    "payment": {
        "status": "CAPTURED"
    }
}
```

---

## Résultats observés (exécution du 2026-04-25)

| Étape | Résultat |
|-------|----------|
| Health checks (x5) | ✅ Tous OK |
| `POST /demo/request-ride` | ✅ `ASSIGNED`, paiement `AUTHORIZED`, prix $15.00 |
| Chauffeur Alice réservée | ✅ `available=false` confirmé via Identity |
| `PATCH → ACCEPTED` | ✅ Statut `ACCEPTED` |
| `PATCH → STARTED` | ✅ Statut `STARTED` |
| `PATCH → COMPLETED` | ✅ Statut `COMPLETED`, paiement `CAPTURED`, chauffeur libéré |
| Projection finale | ✅ État final cohérent |

## En cas d'échec

```bash
docker compose logs gateway
docker compose logs ride
docker compose logs payment
```
