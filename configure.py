#!/usr/bin/env python3
"""Интерактивная настройка Golovach. Запуск: python configure.py"""
from __future__ import annotations
import json, sys
from pathlib import Path

try:
    import questionary
    from questionary import Choice
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except ImportError:
    print("pip install questionary rich httpx")
    sys.exit(1)

try:
    import httpx
except ImportError:
    httpx = None

console = Console()
ROOT = Path(__file__).parent
ENV_PATH = ROOT / ".env"
PROVIDERS_JSON = ROOT / "providers.json"
SETTINGS_JSON = ROOT / "settings.json"

ROLES = [
    ("classifier", "Classifier — классификация"),
    ("orchestrator", "Orchestrator — планирование"),
    ("coder_a", "Coder A — разработчик 1"),
    ("coder_b", "Coder B — разработчик 2"),
    ("critic", "Critic — ревьюер"),
    ("judge", "Judge — арбитр"),
]

PRESETS = {
    "Groq": "https://api.groq.com/openai/v1",
    "Cerebras": "https://api.cerebras.ai/v1",
    "OpenRouter": "https://openrouter.ai/api/v1",
    "Together": "https://api.together.xyz/v1",
    "OpenAI": "https://api.openai.com/v1",
    "Ввести вручную": "__manual__",
}

DEFAULT_SETTINGS = {
    "debate_rounds": 1, "request_timeout": 120,
    "temperature": {"classifier": 0.0, "orchestrator": 0.4, "coder_a": 0.3, "coder_b": 0.3, "critic": 0.5, "judge": 0.2},
    "max_tokens": {"classifier": 10, "orchestrator": 2048, "coder_a": 4096, "coder_b": 4096, "critic": 2048, "judge": 4096},
    "judge_mode": "merge_or_pick", "response_language": "ru",
    "streaming_enabled": True, "parallel_coders": True,
    "show_thinking_in_tg": False, "max_input_length": 10000,
    "anti_fluff_enabled": True, "custom_prompts": {},
}

def load_providers():
    if PROVIDERS_JSON.exists():
        try: return json.loads(PROVIDERS_JSON.read_text("utf-8")) or []
        except: pass
    return []

def save_providers(p):
    PROVIDERS_JSON.write_text(json.dumps(p, indent=2, ensure_ascii=False)+"\n", "utf-8")

def load_settings():
    if SETTINGS_JSON.exists():
        try:
            d = json.loads(SETTINGS_JSON.read_text("utf-8"))
            m = {**DEFAULT_SETTINGS}
            for k,v in d.items():
                if isinstance(v,dict) and isinstance(m.get(k),dict): m[k]={**m[k],**v}
                else: m[k]=v
            return m
        except: pass
    return {**DEFAULT_SETTINGS}

def save_settings(s):
    SETTINGS_JSON.write_text(json.dumps(s, indent=2, ensure_ascii=False)+"\n", "utf-8")

def load_env():
    d = {}
    if ENV_PATH.exists():
        for l in ENV_PATH.read_text("utf-8").splitlines():
            l=l.strip()
            if not l or l.startswith("#") or "=" not in l: continue
            k,_,v=l.partition("="); d[k.strip()]=v.strip().strip('"').strip("'")
    return d

def save_env(d):
    lines=["# Golovach .env",""]
    for k,v in d.items(): lines.append(f"{k}={v}")
    ENV_PATH.write_text("\n".join(lines)+"\n","utf-8")

def fetch_models(url, key):
    if not url or not key: return []
    try:
        if httpx:
            r=httpx.get(url.rstrip("/")+"/models", headers={"Authorization":f"Bearer {key}"}, timeout=15)
            r.raise_for_status(); data=r.json()
        else:
            import urllib.request
            req=urllib.request.Request(url.rstrip("/")+"/models", headers={"Authorization":f"Bearer {key}"})
            with urllib.request.urlopen(req,timeout=15) as resp: data=json.loads(resp.read())
    except Exception as e:
        console.print(f"  [yellow]Ошибка: {e}[/yellow]"); return []
    items=data.get("data") or data.get("models") or []
    ids=[]
    for it in items:
        if isinstance(it,dict): mid=it.get("id") or it.get("name"); ids.append(str(mid)) if mid else None
        elif isinstance(it,str): ids.append(it)
    return sorted(set(ids))

def add_provider(providers):
    console.print("\n[bold cyan]═ Добавление провайдера ═[/bold cyan]")
    name=questionary.text("Имя (напр. kiro, groq):").ask()
    if not name: return
    name=name.strip().lower().replace(" ","_")
    if any(p["name"]==name for p in providers):
        console.print(f"  [yellow]'{name}' уже есть[/yellow]"); return
    preset=questionary.select("Провайдер:", choices=[Choice(k,v) for k,v in PRESETS.items()]).ask()
    if not preset: return
    if preset=="__manual__":
        url=questionary.text("Base URL:").ask()
        if not url: return
    else: url=preset
    key=questionary.password("API Key:").ask()
    if not key: return
    p={"name":name,"base_url":url.strip(),"api_key":key.strip(),"available_models":[],"enabled_models":[]}
    console.print("  [dim]Ищу модели...[/dim]")
    models=fetch_models(p["base_url"],p["api_key"])
    if models:
        console.print(f"  [green]Найдено: {len(models)}[/green]")
        p["available_models"]=models
        sel=questionary.checkbox(f"Включить модели (Space=вкл/выкл):", choices=[Choice(m,m,checked=True) for m in models]).ask()
        p["enabled_models"]=sel if sel else models
        console.print(f"  [green]Активных: {len(p['enabled_models'])}[/green]")
    else:
        console.print("  [yellow]Моделей не найдено (введёшь вручную позже)[/yellow]")
    providers.append(p)
    console.print(f"  [green]'{name}' добавлен![/green]")

def manage_models(providers):
    if not providers: console.print("  [yellow]Нет провайдеров[/yellow]"); return
    choices=[Choice(f"{p['name']} ({len(p.get('enabled_models',[]))} акт.)",i) for i,p in enumerate(providers)]
    choices.append(Choice("← назад",None))
    idx=questionary.select("Провайдер:",choices=choices).ask()
    if idx is None: return
    p=providers[idx]; all_m=p.get("available_models",[]); enabled=set(p.get("enabled_models",[]))
    if not all_m:
        if questionary.confirm("Обновить список?",default=True).ask():
            all_m=fetch_models(p["base_url"],p["api_key"]); p["available_models"]=all_m; enabled=set(all_m)
    if not all_m: return
    sel=questionary.checkbox("Модели (Space=вкл/выкл):", choices=[Choice(m,m,checked=m in enabled) for m in all_m]).ask()
    if sel is not None: p["enabled_models"]=sel; console.print(f"  [green]Активных: {len(sel)}[/green]")

def assign_roles(providers, role_map):
    if not providers: console.print("  [red]Сначала добавь провайдера![/red]"); return
    while True:
        console.print("\n[bold]Роли:[/bold]")
        t=Table(); t.add_column("Роль"); t.add_column("Модель")
        for k,title in ROLES: t.add_row(title.split("—")[0].strip(), role_map.get(k,"[red]—[/red]"))
        console.print(t)
        rc=[Choice(f"{title} [{role_map.get(k,'—')}]",k) for k,title in ROLES]+[Choice("← назад",None)]
        pick=questionary.select("Роль:",choices=rc).ask()
        if not pick: return
        all_m=[Choice(f"[{p['name']}] {m}",f"{p['name']}/{m}") for p in providers for m in p.get("enabled_models",[])]
        all_m.insert(0,Choice("[ввести вручную]","__manual__"))
        cur=role_map.get(pick,"")
        if cur: all_m.insert(0,Choice(f"[оставить] {cur}","__keep__"))
        sel=questionary.select(f"Модель для {pick}:",choices=all_m,use_search_filter=True,use_jk_keys=False).ask()
        if sel is None or sel=="__keep__": continue
        if sel=="__manual__":
            pn=questionary.select("Провайдер:",[Choice(p["name"],p["name"]) for p in providers]).ask()
            if not pn: continue
            mn=questionary.text("Имя модели:").ask()
            if not mn: continue
            sel=f"{pn}/{mn.strip()}"
        role_map[pick]=sel; console.print(f"  [green]{pick} → {sel}[/green]")

def edit_infra(settings):
    while True:
        a=questionary.select("Инфраструктура:", choices=[
            Choice("Раунды дебата","rounds"), Choice("Режим судьи","judge"),
            Choice("Температура по ролям","temp"), Choice("Max tokens","tokens"),
            Choice("Стриминг","stream"), Choice("Параллельность кодеров","par"),
            Choice("Язык ответов","lang"), Choice("Anti-fluff","af"),
            Choice("Таймаут LLM","timeout"), Choice("Кастомные промпты","prompts"),
            Choice("← назад",None),
        ]).ask()
        if not a: return
        if a=="rounds":
            v=questionary.text("Раунды (0-10):",default=str(settings.get("debate_rounds",1))).ask()
            if v and v.isdigit(): settings["debate_rounds"]=int(v)
        elif a=="judge":
            m=questionary.select("Режим:", choices=[
                Choice("merge_or_pick","merge_or_pick"),Choice("approve_or_reject","approve_or_reject"),Choice("rewrite","rewrite")
            ]).ask()
            if m: settings["judge_mode"]=m
        elif a=="temp":
            temps=settings.get("temperature",{})
            for k,title in ROLES:
                v=questionary.text(f"  {title.split('—')[0].strip()} (0.0-2.0):",default=str(temps.get(k,0.5))).ask()
                if v:
                    try: temps[k]=float(v)
                    except: pass
            settings["temperature"]=temps
        elif a=="tokens":
            tok=settings.get("max_tokens",{})
            for k,title in ROLES:
                v=questionary.text(f"  {title.split('—')[0].strip()}:",default=str(tok.get(k,4096))).ask()
                if v and v.isdigit(): tok[k]=int(v)
            settings["max_tokens"]=tok
        elif a=="stream":
            settings["streaming_enabled"]=questionary.confirm("Стримить?",default=settings.get("streaming_enabled",True)).ask()
        elif a=="par":
            settings["parallel_coders"]=questionary.confirm("Параллельно?",default=settings.get("parallel_coders",True)).ask()
        elif a=="lang":
            l=questionary.select("Язык:",choices=[Choice("Русский","ru"),Choice("English","en"),Choice("Авто","auto")]).ask()
            if l: settings["response_language"]=l
        elif a=="af":
            settings["anti_fluff_enabled"]=questionary.confirm("Anti-fluff?",default=settings.get("anti_fluff_enabled",True)).ask()
        elif a=="timeout":
            v=questionary.text("Таймаут (сек):",default=str(settings.get("request_timeout",120))).ask()
            if v and v.isdigit(): settings["request_timeout"]=int(v)
        elif a=="prompts":
            prompts=settings.get("custom_prompts",{})
            for key in ["classifier","orchestrator","coder","critic","judge"]:
                cur=prompts.get(key,"")
                v=questionary.text(f"  Доп. промпт для {key} (Enter=пропуск):",default=cur,multiline=True).ask()
                if v is not None: prompts[key]=v.strip()
            settings["custom_prompts"]=prompts

def main():
    console.print(Panel.fit("[bold]Golovach — настройка AI-команды[/bold]", border_style="cyan"))
    providers=load_providers(); settings=load_settings(); env=load_env()
    role_map={k:env.get(f"{k.upper()}_MODEL","") for k,_ in ROLES if env.get(f"{k.upper()}_MODEL")}

    while True:
        if providers:
            t=Table(title="Провайдеры"); t.add_column("Имя"); t.add_column("URL"); t.add_column("Акт.")
            for p in providers: t.add_row(p["name"],p["base_url"],str(len(p.get("enabled_models",[]))))
            console.print(t)
        a=questionary.select("Меню:", choices=[
            Choice("Добавить провайдера","add"), Choice("Управление моделями (вкл/выкл)","manage"),
            Choice("Назначить модели на роли","roles"), Choice("Настройки инфраструктуры","infra"),
            Choice("Telegram token","tg"), Choice("Посмотреть итог","sum"),
            Choice("— Сохранить и выйти","save"), Choice("— Выйти без сохранения","quit"),
        ]).ask()
        if a=="quit":
            if questionary.confirm("Без сохранения?",default=False).ask(): return
        elif a=="add": add_provider(providers)
        elif a=="manage": manage_models(providers)
        elif a=="roles": assign_roles(providers, role_map)
        elif a=="infra": edit_infra(settings)
        elif a=="tg":
            v=questionary.text("Bot Token:",default=env.get("TELEGRAM_BOT_TOKEN","")).ask()
            if v: env["TELEGRAM_BOT_TOKEN"]=v.strip()
            v=questionary.text("Admin IDs (через запятую):",default=env.get("ADMIN_IDS","")).ask()
            if v is not None: env["ADMIN_IDS"]=v.strip()
        elif a=="sum":
            for k,title in ROLES: console.print(f"  {title.split('—')[0].strip()}: {role_map.get(k,'—')}")
        elif a=="save":
            save_providers(providers); save_settings(settings)
            for k,_ in ROLES: env[f"{k.upper()}_MODEL"]=role_map.get(k,"")
            env["DEBATE_ROUNDS"]=str(settings.get("debate_rounds",1))
            env["REQUEST_TIMEOUT"]=str(settings.get("request_timeout",120))
            save_env(env)
            console.print("[bold green]Сохранено! Запускай: python main.py[/bold green]"); return

if __name__=="__main__":
    try: main()
    except KeyboardInterrupt: console.print("\n[yellow]Прервано[/yellow]")
