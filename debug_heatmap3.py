from app import app
from admin_analyse import heatmap_data
from flask import Flask

with app.app_context():
    # Test de heatmap_data en mode broad
    from flask import request

    # Simuler une requête GET avec paramètres
    with app.test_request_context('/api/heatmap?mode=broad'):
        try:
            result = heatmap_data()
            print("=== Résultat de heatmap_data() ===")
            print(f"Type du résultat: {type(result)}")

            # Si c'est une réponse Flask, récupérer le data
            if hasattr(result, 'get_data'):
                html_content = result.get_data(as_text=True)
            elif isinstance(result, tuple):
                # render_template peut retourner un tuple dans certains cas
                html_content = result[0] if result else ""
            else:
                html_content = str(result)

            print(f"Longueur du HTML: {len(html_content)}")

            # Chercher les totaux dans le HTML
            import re
            totals = re.findall(r'<strong>(\d+)</strong>', html_content)
            print(f"Totaux trouvés dans le HTML: {totals}")

            # Chercher les valeurs des cellules
            cells = re.findall(r'<span class="cell-count">(\d+)</span>', html_content)
            print(f"Valeurs des cellules (premières 10): {cells[:10]}")
            print(f"Nombre total de cellules avec valeurs: {len(cells)}")

            # Chercher les td row-total
            row_totals = re.findall(r'<td class="row-total"><strong>(\d+)</strong></td>', html_content)
            print(f"Totaux de lignes trouvés: {row_totals}")

            # Chercher les th avec des nombres (totaux de colonnes)
            col_totals = re.findall(r'<th>(\d+)</th>', html_content)
            print(f"Totaux de colonnes trouvés: {col_totals}")

        except Exception as e:
            print(f"Erreur: {e}")
            import traceback
            traceback.print_exc()
