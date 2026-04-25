# RideNow - Projet 3 Microservices

Preuve de concept microservices pour le cas d'étude **RideNow** du cours **MGL7361**.

## Objectif couvert
- Décomposition en **services autonomes**
- Communication **REST/JSON** entre services via un gateway orchestrateur
- **Persistance locale par service** (SQLite distincte par service)
- Effets observables via réponses HTTP, logs et base de données
- **Dashboard interactif** pour visualiser et piloter le flux en temps réel

## Services

| Service | Port | Rôle |
|---------|------|------|
| **Gateway** | 8000 | Point d'entrée unique, orchestration, timeout/retry |
| **Identity** | 8001 | Passagers, chauffeurs, disponibilité |
| **Pricing** | 8002 | Prix fixes par paire de zones |
| **Ride** | 8003 | Cycle de vie de la course (machine d'état) |
| **Payment** | 8004 | Autorisation et capture de paiement (mock) |

## Données de démonstration

**Passagers :** Paul (id=100), Mia (id=101)

**Chauffeurs :**
| ID | Nom | Zone | Disponible |
|----|-----|------|-----------|
| 1 | Alice Driver | A | ✓ |
| 2 | Bob Driver | B | ✗ |
| 3 | Charlie Driver | A | ✓ |
| 4 | Diana Driver | C | ✓ |
| 5 | Eve Driver | D | ✓ |

**Zones & prix :** A, B, C, D — tarifs croisés (ex. A→B $15, A→D $25, C→D $12)

## Lancement

```bash
docker compose up --build
```

## Dashboard

Ouvrir **http://localhost:8000/** dans un navigateur.

Le dashboard affiche en temps réel :
- **Santé** des 5 services (rafraîchissement automatique)
- **Tableau des chauffeurs** avec statut disponible/en course
- **Formulaire** de création de course (passager + zones A/B/C/D)
- **Machine d'état** de la course avec progression visuelle
- **Journal d'activité** des appels API avec service(s) impliqué(s)
- **Mode automatique** — enchaîne les transitions avec délai configurable

## Flux nominal

1. `POST /demo/request-ride` — valide passager, trouve chauffeur, calcule prix, crée course (ASSIGNED), autorise paiement, réserve chauffeur
2. `PATCH /demo/rides/{id}/status` `{"status":"ACCEPTED"}`
3. `PATCH /demo/rides/{id}/status` `{"status":"STARTED"}`
4. `PATCH /demo/rides/{id}/status` `{"status":"COMPLETED"}` — capture paiement, libère chauffeur

Machine d'état : `ASSIGNED → ACCEPTED → STARTED → COMPLETED` (ou `CANCELLED`)

## Via curl

```bash
# Créer une course
curl -X POST http://localhost:8000/demo/request-ride \
  -H "Content-Type: application/json" \
  -d '{"passenger_id":100,"from_zone":"A","to_zone":"B"}'

# Progresser les statuts
curl -X PATCH http://localhost:8000/demo/rides/1/status \
  -H "Content-Type: application/json" \
  -d '{"status":"ACCEPTED"}'

# Projection finale
curl http://localhost:8000/demo/rides/1
```

Le fichier `demo.http` contient le scénario complet (compatible VS Code REST Client).

## Observabilité

- Logs Python par service dans stdout Docker (`docker compose logs -f`)
- Documentation OpenAPI : http://localhost:8000/docs à http://localhost:8004/docs
- Journal d'activité en temps réel dans le dashboard (`GET /`)

## Robustesse

- Timeout configurable : variable d'environnement `REQUEST_TIMEOUT_SECONDS` (défaut 3s)
- Retry simple : `RETRY_COUNT` (défaut 1) avec backoff 0.2s
- Codes HTTP cohérents : `201`, `200`, `400`, `404`, `409`, `504`

## Diagrammes

Disponibles dans `docs/` (format draw.io — importer dans app.diagrams.net) :

| Fichier | Description |
|---------|-------------|
| `architecture-diagram.drawio` | Vue d'architecture en couches (client · gateway · services · persistance) |
| `component-diagram.drawio` | Diagramme de composants UML avec interfaces et bases de données |
| `sequence-diagram.drawio` | Diagramme de séquence du flux nominal complet |
| `architecture_diagram.svg` | Vue d'ensemble SVG (original) |

## Tests

Voir `TestPlan.md` pour le plan de test manuel du flux nominal avec commandes curl et résultats attendus.
