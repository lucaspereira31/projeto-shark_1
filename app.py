from flask import Flask, render_template, request, redirect, url_for, session
import os
import mysql.connector
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime, date
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = "shark_foodtruck_key"

menu = {
    "ZOIÃO SIMPLES": 17.00, "BURGUER": 20.00, "SALADA": 22.00,
    "CHEDDAR": 22.00, "FRANGUITO": 22.00, "PORQUINHO": 22.00,
    "BURGUER A CAVALO": 25.00, "BACON": 28.00, "TUDO": 30.00,
    "MEGA TUDO": 42.00, "BIG ZOIÃO": 35.00, "TRIO PARADA DURA": 52.00
}

def get_db_connection():
    try:
        return mysql.connector.connect(
            host=os.environ.get("DB_HOST", "foodtruck-mysql"),
            user=os.environ.get("DB_USER", "root"),
            password=os.environ.get("DB_PASSWORD", "root"),
            database=os.environ.get("DB_NAME", "foodtruck"),
            port=int(os.environ.get("DB_PORT", 3306))
        )
    except mysql.connector.Error as err:
        print(f"Erro ao conectar ao banco de dados: {err}")
        raise err

def get_produto_id(cursor, nome, preco):
    cursor.execute("SELECT id_produtos FROM produtos WHERE nome = %s", (nome,))
    row = cursor.fetchone()
    if row: return row[0]
    cursor.execute("INSERT INTO produtos (nome, preco) VALUES (%s, %s)", (nome, preco))
    return cursor.lastrowid

@app.route("/", methods=["GET", "POST"])
def index():
    if "pedido" not in session: session["pedido"] = []
    if "cliente" not in session: session["cliente"] = {"nome": "Consumidor", "telefone": ""}
    
    pedidos_status = []
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id_pedidos, nome_cliente, hora_pedido FROM pedidos WHERE status != 'entregue' ORDER BY hora_pedido ASC")
        pedidos_db = cursor.fetchall()
        agora = datetime.now()
        for p in pedidos_db:
            minutos = int((agora - p["hora_pedido"]).total_seconds() / 60)
            status_texto, classe = ("Em Preparo", "status-preparo") if minutos <= 15 else ("Pendente", "status-atrasado")
            pedidos_status.append({"id": p["id_pedidos"], "cliente": p["nome_cliente"], "minutos": minutos, "status": status_texto, "classe": classe})
        cursor.close()
        conn.close()

    if request.method == "POST":
        if "nome_cliente" in request.form:
            session["cliente"] = {"nome": request.form.get("nome_cliente") or "Consumidor", "telefone": request.form.get("telefone_cliente") or ""}
        elif "item" in request.form:
            item_nome, qty = request.form.get("item"), request.form.get("quantidade", type=int)
            if item_nome in menu and qty > 0:
                pedido_atual = session["pedido"]
                pedido_atual.append({"item": item_nome, "quantidade": qty, "preco": menu[item_nome]})
                session["pedido"] = pedido_atual
        session.modified = True
        return redirect(url_for("index"))

    total = sum(item["quantidade"] * item["preco"] for item in session["pedido"])
    ticket_id = request.args.get('ticket')
    return render_template("index.html", menu=menu, pedido=session["pedido"], total=total, cliente=session["cliente"], pedidos_vivos=pedidos_status, ticket_id=ticket_id)

@app.route("/pagamento", methods=["POST"])
def pagamento():
    if not session.get("pedido"): return redirect(url_for("index"))
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            total = sum(item["quantidade"] * item["preco"] for item in session["pedido"])
            sql = "INSERT INTO pedidos (nome_cliente, total, status, hora_pedido) VALUES (%s, %s, %s, %s)"
            cursor.execute(sql, (session["cliente"]["nome"], total, "preparo", datetime.now()))
            pedido_id = cursor.lastrowid
            for item in session["pedido"]:
                prod_id = get_produto_id(cursor, item["item"], item["preco"])
                cursor.execute("INSERT INTO itens_pedido (quantidade, preco_unitario, pedidos_id_pedidos, produtos_id_produtos) VALUES (%s, %s, %s, %s)", (item["quantidade"], item["preco"], pedido_id, prod_id))
            conn.commit()
            session.pop("pedido", None)
            return redirect(url_for("index", ticket=pedido_id))
        except Exception as e:
            return f"Erro no banco: {e}", 500
        finally:
            conn.close()
    return "Erro de conexão", 500

@app.route("/imprimir_ticket/<int:pedido_id>")
def imprimir_ticket(pedido_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id_pedidos, nome_cliente, total, hora_pedido FROM pedidos WHERE id_pedidos = %s", (pedido_id,))
    pedido = cursor.fetchone()
    cursor.execute("SELECT i.quantidade, i.preco_unitario, p.nome FROM itens_pedido i JOIN produtos p ON i.produtos_id_produtos = p.id_produtos WHERE i.pedidos_id_pedidos = %s", (pedido_id,))
    itens = cursor.fetchall()
    conn.close()
    return render_template("ticket.html", pedido=pedido, itens=itens)

@app.route("/entregar/<int:id>")
def marcar_entregue(id):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE pedidos SET status = 'entregue' WHERE id_pedidos = %s", (id,))
        conn.commit()
        conn.close()
    return redirect(url_for("index"))

@app.route('/limpar_pedido')
def limpar_pedido():
    session.pop('pedido', None)
    return redirect(url_for('index'))

@app.route('/estoque')
def estoque():
    conn = get_db_connection()
    itens_estoque = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT idinsumos, nome, unidade_medida, quantidade_estoque FROM insumos")
        itens_estoque = cursor.fetchall()
        cursor.close()
        conn.close()
    return render_template("estoque.html", estoque=itens_estoque)

@app.route('/atualizar_estoque', methods=['POST'])
def atualizar_estoque():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        for key, value in request.form.items():
            if key.startswith('qtd_') and value:
                id_insumo = key.replace('qtd_', '')
                nova_qtd = value
                cursor.execute("UPDATE insumos SET quantidade_estoque = %s WHERE idinsumos = %s", 
                               (nova_qtd, id_insumo))
        conn.commit()
        cursor.close()
        conn.close()
    return redirect(url_for('estoque'))

@app.route('/cadastrar_item_estoque', methods=['POST'])
def cadastrar_item_estoque():
    nome = request.form.get('nome')
    unidade = request.form.get('unidade')
    quantidade = request.form.get('quantidade')

    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        # CORREÇÃO AQUI: Mudado de 'unity' para 'unidade'
        cursor.execute("INSERT INTO insumos (nome, unidade_medida, quantidade_estoque) VALUES (%s, %s, %s)", 
                       (nome, unidade, quantidade))
        conn.commit()
        cursor.close()
        conn.close()
    return redirect(url_for('estoque'))

@app.route('/relatorios')
def relatorios():
    conn = get_db_connection()
    vendas_diarias_db = []
    total_custos = 0.0

    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            
            # 1. Busca agrupada de vendas dos últimos 7 dias usando sintaxe MySQL (DAYNAME)
            cursor.execute("""
                SELECT DAYNAME(hora_pedido) AS dia_nome, SUM(total) AS total_dia 
                FROM pedidos 
                WHERE hora_pedido >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                GROUP BY DAYNAME(hora_pedido), DATE(hora_pedido)
                ORDER BY DATE(hora_pedido) ASC
            """)
            vendas_diarias_db = cursor.fetchall()
            
            # 2. Busca a soma real de despesas da tabela custos
            cursor.execute("SELECT SUM(valor) AS total_gastos FROM custos")
            res_custos = cursor.fetchone()
            if res_custos and res_custos['total_gastos']:
                total_custos = float(res_custos['total_gastos'])
                
            cursor.close()
        except Exception as e:
            print(f"Erro na query de relatórios: {e}")
        finally:
            conn.close()

    # Dicionário para traduzir o retorno do MySQL para português curto
    traducao_dias = {
        'Monday': 'Seg', 'Tuesday': 'Ter', 'Wednesday': 'Qua', 
        'Thursday': 'Qui', 'Friday': 'Sex', 'Saturday': 'Sáb', 'Sunday': 'Dom'
    }

    dias = []
    vendas_diarias = []

    # Extrai os dados do banco para os arrays do gráfico
    for linha in vendas_diarias_db:
        dia_pt = traducao_dias.get(linha['dia_nome'], linha['dia_nome'])
        dias.append(dia_pt)
        vendas_diarias.append(float(linha['total_dia']) if linha['total_dia'] else 0.0)

    # Fallback/Padrão caso não existam vendas cadastradas nos últimos 7 dias
    if not dias:
        dias = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
        vendas_diarias = [0.0] * 7

    # Cálculos finais dos cards informativos
    total_vendas = sum(vendas_diarias)
    lucro_liquido = total_vendas - total_custos

    return render_template(
        'relatorios.html', 
        total_vendas=total_vendas, 
        total_custos=total_custos, 
        lucro_liquido=lucro_liquido,
        dias=dias,
        vendas_diarias=vendas_diarias
    )

@app.route('/custos')
def custos():
    conn = get_db_connection()
    vendas_totais = 0.0
    lista_custos = []
    lucro_final = 0.0
    
    if conn:
        cursor = conn.cursor(dictionary=True)
        
        # --- MISSÃO 1: Soma as vendas (Fica igualzinho) ---
        cursor.execute("SELECT SUM(total) FROM pedidos")
        res_vendas = cursor.fetchone()
        vendas_totais = float(res_vendas['SUM(total)']) if res_vendas['SUM(total)'] else 0.0
        
        # --- MISSÃO 2: Busca os custos (ADICIONADO O id_custo AQUI) ---
        # Antes estava: SELECT descricao, valor...
        cursor.execute("SELECT * FROM custos ORDER BY data_custo DESC")
        lista_custos = cursor.fetchall()
        
        # Calcula o lucro descontando as despesas
        total_gastos = sum(float(c['valor']) for c in lista_custos)
        lucro_final = vendas_totais - total_gastos
        
        cursor.close()
        conn.close()
    
    return render_template('custos.html', vendas=vendas_totais, custos_lista=lista_custos, lucro=lucro_final)

@app.route('/salvar_custos', methods=['POST'])
def salvar_custos():
    nome = request.form.get('nome_custo')
    valor = request.form.get('valor_custo')

    if nome and valor:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO custos (descricao, valor, data_custo) VALUES (%s, %s, %s)", 
                           (nome, valor, date.today()))
            conn.commit()
            cursor.close()
            conn.close()
    return redirect(url_for('custos'))

@app.route('/excluir-custo/<int:id>')
def excluir_custo(id):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        
        # Como não temos certeza se é id, id_custo ou idcustos, 
        # vamos descobrir o nome real da primeira coluna da tabela custos:
        cursor.execute("SHOW COLUMNS FROM custos")
        colunas = cursor.fetchall()
        nome_da_chave_primaria = colunas[0][0] # Pega o nome da primeira coluna da tabela
        
        # Agora deleta usando o nome real que está no banco da Aiven
        query = f"DELETE FROM custos WHERE {nome_da_chave_primaria} = %s"
        cursor.execute(query, (id,))
        
        conn.commit()
        cursor.close()
        conn.close()
    return redirect(url_for('custos'))
@app.route('/excluir-estoque/<int:id>')
def excluir_estoque(id):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        # Deleta o insumo usando a chave primária correta: idinsumos
        cursor.execute("DELETE FROM insumos WHERE idinsumos = %s", (id,))
        conn.commit()
        cursor.close()
        conn.close()
    return redirect(url_for('estoque'))


if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=porta)