from app import app
from flask import render_template_string

with app.app_context():
    # Test du template corrigé avec les données
    template_content = '''{% if theme_columns and diff_rows %}
<table>
    <tbody>
        {% for d in diff_rows %}
        <tr>
            <th>{{ d }}</th>
            {% set row_values = [] %}
            {% for col in theme_columns %}
                {% set val = counts.get(d, {}).get(col.id, 0) %}
                {% set _ = row_values.append(val) %}
                <td>{{ val }}</td>
            {% endfor %}
            {% set row_total = row_values | sum %}
            <td class="row-total"><strong>{{ row_total }}</strong></td>
        </tr>
        {% endfor %}
    </tbody>
    <tfoot>
        <tr>
            <th>Total</th>
            {% set col_totals = [] %}
            {% for col in theme_columns %}
                {% set col_values = [] %}
                {% for d in diff_rows %}
                    {% set _ = col_values.append(counts.get(d, {}).get(col.id, 0)) %}
                {% endfor %}
                {% set col_total = col_values | sum %}
                {% set _ = col_totals.append(col_total) %}
                <th>{{ col_total }}</th>
            {% endfor %}
            {% set grand_total = col_totals | sum %}
            <th>{{ grand_total }}</th>
        </tr>
    </tfoot>
</table>
{% endif %}'''

    # Données de test
    theme_columns = [
        {'id': 6, 'name': 'Communautés'},
        {'id': 4, 'name': 'Histoire'},
        {'id': 1, 'name': 'Règles'},
        {'id': 5, 'name': 'Technique'},
        {'id': 2, 'name': 'Terminologie'},
        {'id': 8, 'name': 'Test'},
        {'id': 3, 'name': 'Types de caches'}
    ]
    diff_rows = [1, 2, 3, 4, 5]
    counts = {
        1: {1: 13, 2: 9, 3: 12, 4: 9, 5: 8, 6: 8},
        2: {1: 12, 2: 8, 3: 13, 4: 8, 5: 8, 6: 8},
        3: {1: 12, 2: 8, 3: 12, 4: 8, 5: 8, 6: 8},
        4: {1: 12, 2: 8, 3: 12, 4: 8, 5: 8, 6: 8},
        5: {1: 12, 2: 8, 3: 12, 4: 8, 5: 8, 6: 8}
    }

    try:
        result = render_template_string(template_content,
                                      theme_columns=theme_columns,
                                      diff_rows=diff_rows,
                                      counts=counts)
        print('Template rendu avec succès')

        # Chercher les totaux de lignes
        import re
        row_totals = re.findall(r'<td class="row-total"><strong>(\d+)</strong></td>', result)
        print(f'Totaux de lignes: {row_totals}')

        # Chercher les totaux de colonnes et grand total
        col_totals = re.findall(r'<th>(\d+)</th>', result)
        print(f'Totaux de colonnes: {col_totals}')

    except Exception as e:
        print(f'Erreur: {e}')
        import traceback
        traceback.print_exc()
