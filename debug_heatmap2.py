from app import app
from admin_analyse import heatmap_data
from flask import Flask
import io
import sys

# Capture la sortie du render_template
class Capturing(list):
    def __enter__(self):
        self._stdout = sys.stdout
        sys.stdout = self._stringio = io.StringIO()
        return self
    def __exit__(self, *args):
        self.extend(self._stringio.getvalue().splitlines())
        sys.stdout = self._stdout

with app.app_context():
    # Test de heatmap_data en mode broad
    from flask import request
    import flask

    # Simuler une requête GET avec paramètres
    with app.test_request_context('/api/heatmap?mode=broad'):
        try:
            result = heatmap_data()
            print("=== Résultat de heatmap_data() ===")
            print(f"Type du résultat: {type(result)}")
            print(f"Contenu (premiers 500 chars): {str(result)[:500]}")

            # Chercher les totaux dans le HTML
            html_content = str(result)
            import re
            totals = re.findall(r'<strong>(\d+)</strong>', html_content)
            print(f"\nTotaux trouvés dans le HTML: {totals}")

            # Chercher les valeurs des cellules
            cells = re.findall(r'<span class="cell-count">(\d+)</span>', html_content)
            print(f"Valeurs des cellules (premières 10): {cells[:10]}")

        except Exception as e:
            print(f"Erreur: {e}")
            import traceback
            traceback.print_exc()
