# Radar Vidéo France

Carte de France : zoome sur une zone ou touche une ville, les vidéos YouTube du jour choisi
apparaissent dans la liste et sur la carte. Elles se lisent directement dans le site.

## 1. Clé API YouTube (gratuite, 5 min)
1. https://console.cloud.google.com → crée un projet.
2. « API et services » → « Bibliothèque » → active **YouTube Data API v3**.
3. « Identifiants » → « Créer des identifiants » → **Clé API**.
4. Copie `.env.example` en `.env` et colle la clé : `YT_API_KEY=...`

## 2. Lancer
```
pip install -r requirements.txt
python app.py
```
Ouvre http://localhost:5000 (ou http://IP-DU-PC:5000 depuis ton téléphone sur le même Wi-Fi).

## Fonctionnement
- Zoom ≥ 9 : les vidéos géolocalisées de la zone visible se chargent seules (pastilles rouges ▶).
- Touche une ville : recherche par nom de ville (plus de résultats, mais pas toutes placées sur la carte).
- Sujets : actualité, faits divers, météo, manifs, accidents, sport.
- Date : jour précis (de 0h à 24h, heure de Paris).

## Quota
YouTube donne 10 000 unités/jour ; une recherche en coûte ~101, donc ~95 recherches par jour.
Le serveur garde les résultats en cache (20 min pour aujourd'hui, 24 h pour les jours passés)
pour ne pas brûler le quota quand tu bouges un peu la carte. Décoche « Charger quand je déplace
la carte » si tu veux économiser.

## Mettre en ligne (accès partout)
Render.com (gratuit) : nouveau « Web Service » depuis un repo GitHub, commande de démarrage
`pip install -r requirements.txt && python app.py`, variable d'environnement `YT_API_KEY`.
