import json
import re

import pandas as pd
import requests
import typer

URL="https://wger.de/api/v2/"
HEADERS={"User-Agent": "hdhd"}

app = typer.Typer()
@app.callback()
def main():
    pass

def nome_musculo_para_id(nome):
    response = requests.get(URL + "muscle/", headers=HEADERS, params={"limit": 100}, timeout=15)

    if response.status_code != 200:
        print("Erro:", response.status_code)
        raise typer.Exit()

    nome = nome.lower().strip()
    for muscule in response.json()["results"]:
        if (muscule.get("name_en") or "").lower() == nome:
            return muscule["id"]

    return None

def nome_categoria_para_id(nome):
    response = requests.get(URL + "exercisecategory/", headers=HEADERS, params={"limit": 100}, timeout=15)

    if response.status_code != 200:
        print("Erro:", response.status_code)
        raise typer.Exit()

    nome = nome.lower().strip()
    for category in response.json()["results"]:
        if category["name"].lower() == nome:
            return category["id"]

    return None

@app.command()
def top(n: int):
    if n <= 0:
        print("O número de exercícios tem de ser maior que 0.")
        return
    
    parametros = {"language": 2,"limit": n,"ordering": "-created"}
    url=URL + "exerciseinfo/"
    resposta = requests.get(url,headers=HEADERS,params=parametros,timeout=15)
    
    if resposta.status_code == 200:
        
        dados = resposta.json()
        lista_exercicios = []

        for exercicio in dados["results"]:

            traducoes = exercicio["translations"]

            for traducao in traducoes:

                if traducao["language"] == 2:

                    nome = traducao["name"]
                    categoria = exercicio["category"]["name"]

                    equipamento = []

                    for item in exercicio["equipment"]:
                        equipamento.append(item["name"])

                    lista_exercicios.append({"name": nome,"category": categoria,"equipment": equipamento})

                    break

        print(json.dumps(lista_exercicios, ensure_ascii=False).replace("}, {", "},\n{"))

    else:
        print("Erro:", resposta.status_code)

def pesquisar(termo, n, modo="princ", tipo="any"):
    termo = termo.lower().strip()

    filtros = None

    id_muscle = nome_musculo_para_id(termo)
    if id_muscle is not None:
        filtros = [{"muscles": id_muscle}]
        if modo == "all":
            filtros.append({"muscles_secondary": id_muscle})
    else:
        id_category = nome_categoria_para_id(termo)
        if id_category is not None:
            filtros = [{"category": id_category}]

    if filtros is None:
        return None

    lista_exercicios = []
    ids_vistos = set()

    for filtro in filtros:
        parametros = {"language": 2, "limit": max(n, 20), **filtro}
        url = URL + "exerciseinfo/"

        while url and len(lista_exercicios) < n:
            resposta = requests.get(url, headers=HEADERS, params=parametros, timeout=15)

            if resposta.status_code != 200:
                print("Erro:", resposta.status_code)
                raise typer.Exit()

            dados = resposta.json()

            for exercicio in dados["results"]:

                if exercicio["id"] in ids_vistos:
                    continue

                tipo_exercicio = inferir_tipo(exercicio)
                if tipo != "any" and tipo_exercicio != tipo:
                    continue

                for traducao in exercicio["translations"]:

                    if traducao["language"] == 2:

                        ids_vistos.add(exercicio["id"])
                        lista_exercicios.append({
                            "name": traducao["name"],
                            "type": tipo_exercicio,
                            "category": exercicio["category"]["name"],
                            "muscles": [m.get("name_en") or m["name"] for m in exercicio["muscles"]],
                            "equipment": [item["name"] for item in exercicio["equipment"]]
                        })

                        break

                if len(lista_exercicios) >= n:
                    break

            url = dados["next"]
            parametros = None

    return lista_exercicios


@app.command()
def search(termo: str, n: int, modo: str = typer.Argument("princ")):
    if n <= 0:
        print("O número de resultados tem de ser maior que 0.")
        return

    modo = modo.lower().strip()
    if modo not in ("all", "princ"):
        print("O modo tem de ser princ ou all.")
        return

    resultado = pesquisar(termo, n, modo)

    if resultado is None:
        print(f"'{termo}' não é um músculo nem uma categoria válida.")
        return
    if not resultado:
        print(f"Nenhum exercício encontrado para {termo}.")
        return

    print(json.dumps(resultado, ensure_ascii=False).replace("}, {", "},\n{"))


def inferir_tipo(exercicio):
    categoria = exercicio["category"]["name"].lower()

    nome = ""
    descricao = ""
    for traducao in exercicio["translations"]:
        if traducao["language"] == 2:
            nome = traducao["name"].lower()
            descricao = re.sub(r"<[^>]+>", " ", traducao["description"]).lower()
            break

    principais = len(exercicio["muscles"])
    secundarios = len(exercicio["muscles_secondary"])

    if categoria == "cardio":
        return "cardio"
    if principais > 1:
        return "compound"
    if re.search(r"\b(squat|deadlift|press|row|rowing|pull[- ]?up|chin[- ]?up|lunge|dip|clean|snatch|thrust)s?\b", nome):
        return "compound"
    if re.search(r"\b(curl|extension|raise|fly|flye|kickback|crunch|pushdown)s?\b", nome):
        return "isolated"
    if secundarios >= 2:
        return "compound"
    if principais == 1:
        if re.search(r"\b(squat|deadlift|press|row|pull[- ]?up|lunge)\b", descricao):
            return "compound"
        return "isolated"
    return "other"


@app.command("type")
def tipo(exercise_id: int):
    resposta = requests.get(URL + f"exerciseinfo/{exercise_id}/", headers=HEADERS, timeout=15)

    if resposta.status_code == 404:
        print(f"O exercício {exercise_id} não existe.")

        sugestoes = []
        for passo in (-1, 1): 
            outro = exercise_id + passo
            tentativas = 0

            while outro > 0 and tentativas < 20:
                r = requests.get(URL + f"exerciseinfo/{outro}/", headers=HEADERS, timeout=15)

                if r.status_code == 200:
                    nome = None
                    for traducao in r.json()["translations"]:
                        if traducao["language"] == 2:
                            nome = traducao["name"]
                            break

                    if nome:
                        sugestoes.append(f"{outro} - {nome}")
                        break

                outro += passo
                tentativas += 1

        if sugestoes:
            print("IDs mais próximos:")
            for s in sugestoes:
                print(" ", s)
        return
    if resposta.status_code != 200:
        print("Erro:", resposta.status_code)
        return

    print(inferir_tipo(resposta.json()))

@app.command()
def equipment(categoria: str):
    categoria = categoria.lower().strip()

    id_category = nome_categoria_para_id(categoria)
    if id_category is None:
        print(f"{categoria} não é uma categoria válida.")
        return

    padroes = {
        "barbell": r"\bbarbells?\b",
        "dumbbell": r"\bdumb-?bells?\b",
        "cable": r"\bcables?\b",
        "machine": r"\bmachines?\b",
        "bodyweight": r"\bbody-?\s?weight\b",
        "kettlebell": r"\bkettle-?bells?\b",
        "band": r"\b(resistance )?bands?\b",
        "bench": r"\bbench(es)?\b",
        "bar": r"\bbars?\b",
    }

    contagem = {nome: 0 for nome in padroes}

    parametros = {"language": 2, "limit": 100, "category": id_category}
    url = URL + "exerciseinfo/"

    while url:
        resposta = requests.get(url, headers=HEADERS, params=parametros, timeout=15)

        if resposta.status_code != 200:
            print("Erro:", resposta.status_code)
            return

        dados = resposta.json()
        for exercicio in dados["results"]:
            for traducao in exercicio["translations"]:
                if traducao["language"] == 2:
                    descricao = re.sub(r"<[^>]+>", " ", traducao["description"]).lower()
                    for nome, padrao in padroes.items():
                        contagem[nome] += len(re.findall(padrao, descricao))
                    break

        url = dados["next"]
        parametros = None

    ordenado = sorted(contagem.items(), key=lambda x: x[1], reverse=True)
    resultado = [{nome: total} for nome, total in ordenado if total > 0]

    if not resultado:
        print(f"Nenhum equipamento encontrado nas descrições da categoria {categoria}.")
        return

    print(json.dumps(resultado, ensure_ascii=False).replace("}, {", "},\n{"))

@app.command()
def workout(termos: str, tipo: str, n: int, ficheiro: str = typer.Option(None, "--csv")):
    if n <= 0:
        print("O número de exercícios tem de ser maior que 0.")
        return

    tipo = tipo.lower().strip()
    if tipo not in ("compound", "isolated", "any"):
        print("O tipo tem de ser compound, isolated ou any.")
        return

    plano = {}
    for termo in termos.split(","):
        termo = termo.strip().lower()
        if not termo:
            continue

        resultado = pesquisar(termo, n, "princ", tipo)

        if resultado is None:
            print(f"'{termo}' não é um músculo nem uma categoria válida (ignorado).")
            continue

        plano[termo] = resultado

    if not plano:
        return

    if ficheiro:
        linhas = []
        for grupo, exercicios in plano.items():
            for exercicio in exercicios:
                linhas.append({
                    "grupo": grupo,
                    "name": exercicio["name"],
                    "type": exercicio["type"],
                    "category": exercicio["category"],
                    "muscles": "; ".join(exercicio["muscles"]),
                    "equipment": "; ".join(exercicio["equipment"]),
                })

        colunas = ["grupo", "name", "type", "category", "muscles", "equipment"]
        df = pd.DataFrame(linhas, columns=colunas)
        df.to_csv(ficheiro, index=False, encoding="utf-8")

        print(f"Ficheiro exportado: {ficheiro} ({len(df)} registos)")
    else:
        grupos = []
        for grupo, exercicios in plano.items():
            if exercicios:
                linhas = ",\n  ".join(json.dumps(e, ensure_ascii=False) for e in exercicios)
                grupos.append(f'"{grupo}": [\n  {linhas} ]')
            else:
                grupos.append(f'"{grupo}": []')
        print("{ " + ",\n ".join(grupos) + "\n}")



ALIASES_EQUIP = {
    "bodyweight": "none (bodyweight exercise)",
    "none": "none (bodyweight exercise)",
    "no equipment": "none (bodyweight exercise)",
    "pullup bar": "pull-up bar",
    "pull up bar": "pull-up bar",
}


def obter_equipamentos():
    resposta = requests.get(URL + "equipment/", headers=HEADERS, params={"limit": 100}, timeout=15)

    if resposta.status_code != 200:
        print("Erro:", resposta.status_code)
        raise typer.Exit()

    return {e["id"]: e["name"] for e in resposta.json()["results"]}


def obter_musculos():
    resposta = requests.get(URL + "muscle/", headers=HEADERS, params={"limit": 100}, timeout=15)

    if resposta.status_code != 200:
        print("Erro:", resposta.status_code)
        raise typer.Exit()

    return [m.get("name_en") or m["name"] for m in resposta.json()["results"]]


def equipamento_para_ids(texto, todos):
    """Converte 'dumbbell,bench' em {id: nome}. Devolve também os nomes não reconhecidos."""
    escolhidos = {}
    ignorados = []

    for pedido in texto.split(","):
        pedido = pedido.lower().strip()
        if not pedido:
            continue

        pedido = ALIASES_EQUIP.get(pedido, pedido)
        encontrado = None

        for id_, nome in todos.items():
            if nome.lower() == pedido:
                encontrado = id_
                break

        if encontrado is None:
            for id_, nome in todos.items():
                if pedido in nome.lower():
                    encontrado = id_
                    break

        if encontrado is None:
            ignorados.append(pedido)
        else:
            escolhidos[encontrado] = todos[encontrado]

    return escolhidos, ignorados


def formatar_lista(exercicios):
    """Uma lista de exercícios com um exercício por linha (igual ao workout)."""
    if not exercicios:
        return "[]"
    linhas = ",\n  ".join(json.dumps(e, ensure_ascii=False) for e in exercicios)
    return "[\n  " + linhas + " ]"


@app.command()
def home(equipamento: str, n: int):
    if n <= 0:
        print("O número de exercícios tem de ser maior que 0.")
        return

    todos = obter_equipamentos()
    escolhidos, ignorados = equipamento_para_ids(equipamento, todos)

    for nome in ignorados:
        print(f"'{nome}' não é um equipamento válido (ignorado).")

    if not escolhidos:
        print("Equipamentos disponíveis:", ", ".join(sorted(todos.values())))
        return

    permitidos = set(escolhidos.values())
    exercicios = {}

    for id_equip in escolhidos:
        parametros = {"language": 2, "limit": 100, "equipment": id_equip}
        url = URL + "exerciseinfo/"

        while url:
            resposta = requests.get(url, headers=HEADERS, params=parametros, timeout=15)

            if resposta.status_code != 200:
                print("Erro:", resposta.status_code)
                raise typer.Exit()

            dados = resposta.json()

            for exercicio in dados["results"]:
                if exercicio["id"] in exercicios:
                    continue

                # só aceita exercícios cujo equipamento esteja TODO na lista do utilizador
                equip_exercicio = {item["name"] for item in exercicio["equipment"]}
                if not equip_exercicio <= permitidos:
                    continue

                nome = None
                for traducao in exercicio["translations"]:
                    if traducao["language"] == 2:
                        nome = traducao["name"]
                        break

                if nome is None:
                    continue

                exercicios[exercicio["id"]] = {
                    "name": nome,
                    "type": inferir_tipo(exercicio),
                    "category": exercicio["category"]["name"],
                    "muscles": [m.get("name_en") or m["name"] for m in exercicio["muscles"]],
                    "equipment": sorted(equip_exercicio),
                }

            url = dados["next"]
            parametros = None

    lista = list(exercicios.values())

    # músculos treinados (principais) por TODOS os exercícios encontrados
    cobertos = {m for ex in lista for m in ex["muscles"]}
    sem_treino = sorted(m for m in obter_musculos() if m not in cobertos)

    print("{")
    print(f' "equipment_used": {json.dumps(sorted(permitidos), ensure_ascii=False)},')
    print(f' "total_exercises_found": {len(lista)},')
    print(f' "exercises": {formatar_lista(lista[:n])},')
    print(f' "muscles_covered": {json.dumps(sorted(cobertos), ensure_ascii=False)},')
    print(f' "undertrained_muscles": {json.dumps(sem_treino, ensure_ascii=False)}')
    print("}")



SPLITS = {
    2: [
        ("Upper", ["chest", "back", "shoulders", "arms"]),
        ("Lower", ["legs", "calves", "abs"]),
    ],
    3: [
        ("Push", ["chest", "shoulders", "triceps"]),
        ("Pull", ["back", "biceps"]),
        ("Legs", ["legs", "abs"]),
    ],
    4: [
        ("Push", ["chest", "shoulders", "triceps"]),
        ("Pull", ["back", "biceps"]),
        ("Legs", ["legs", "calves"]),
        ("Arms & Core", ["arms", "abs"]),
    ],
    5: [
        ("Chest & Triceps", ["chest", "triceps"]),
        ("Back & Biceps", ["back", "biceps"]),
        ("Legs", ["legs", "calves"]),
        ("Shoulders & Abs", ["shoulders", "abs"]),
        ("Cardio", ["cardio"]),
    ],
}


@app.command()
def week(dias: int, esforco: str = typer.Argument("any"), n: int = typer.Argument(2)):
    if dias not in SPLITS:
        print("O número de dias tem de ser 2, 3, 4 ou 5.")
        return

    if n <= 0:
        print("O número de exercícios por músculo tem de ser maior que 0.")
        return

    esforco = esforco.lower().strip()
    if esforco not in ("compound", "isolated", "any"):
        print("O tipo tem de ser compound, isolated ou any.")
        return

    ja_usados = set()
    plano = {}

    for indice, (nome_dia, termos) in enumerate(SPLITS[dias], start=1):
        dia = {}

        for termo in termos:
            # cardio é sempre tipo "cardio", por isso não se filtra por esforço
            filtro = "any" if termo == "cardio" else esforco

            # pede mais resultados para poder saltar os já usados noutros dias
            candidatos = pesquisar(termo, n * 3, "princ", filtro)
            if not candidatos:
                dia[termo] = []
                continue

            escolhidos = []
            for exercicio in candidatos:
                if exercicio["name"] in ja_usados:
                    continue
                ja_usados.add(exercicio["name"])
                escolhidos.append(exercicio)
                if len(escolhidos) >= n:
                    break

            dia[termo] = escolhidos

        plano[f"Dia {indice} - {nome_dia}"] = dia

    # impressão: um exercício por linha, como no workout
    dias_txt = []
    for nome_dia, grupos in plano.items():
        grupos_txt = []
        for termo, exercicios in grupos.items():
            if exercicios:
                linhas = ",\n    ".join(json.dumps(e, ensure_ascii=False) for e in exercicios)
                grupos_txt.append(f'  "{termo}": [\n    {linhas} ]')
            else:
                grupos_txt.append(f'  "{termo}": []')
        dias_txt.append(f' "{nome_dia}": {{\n' + ",\n".join(grupos_txt) + "\n }")

    print("{\n" + ",\n".join(dias_txt) + "\n}")

if __name__ == "__main__":
    app()