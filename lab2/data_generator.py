import os
import subprocess
import re
import pandas as pd
from itertools import product

# Пути к almaBTE
# alma_path = os.path.expanduser('~/Programs/almabte-v1.3.2/build/src')
# os.environ['PATH'] += os.pathsep + alma_path

project_dir = os.getcwd()

def build_superlattice(R: float, x1: int, x2: int) -> str:
    """Генерация структуры и запуск superlattice_builder.
       Возвращает stem (имя .h5 файла без расширения и размера сетки)."""
    
    total_layers = x1 + x2  # Общее количество слоёв
    layers = []
    
    # Генерируем доли материалов для каждого слоя по модели Мураки
    for lam in range(1, total_layers + 1):
        if lam <= x1:
            # Первые x1 слоёв
            f = 1 - R**lam
        else:
            # Следующие x2 слоёв
            f = (1 - R**x1) * (R**(lam - x1))
        layers.append(f)

    layers_xml = "\n".join([f'  <layer mixfraction="{val:.10f}"/>' for val in layers])

    xml_content = f"""<superlattice>
  <materials_repository root_directory="./data"/>
  <gridDensity A="24" B="24" C="24"/>
  <compound name="AlN_cubic"/>
  <compound name="GaN_cubic"/>
  <normal na="0" nb="0" nc="1" nqline="501"/>
{layers_xml}
  <target directory="./AlN_GaN"/>
</superlattice>
"""
    xml_file = os.path.join(project_dir, f"AlN_GaN_R{R}_x1_{x1}_x2_{x2}.xml")
    with open(xml_file, "w") as f:
        f.write(xml_content)

    print(f"[INFO] Создан {xml_file} с {x1}+{x2} слоями, R={R}")

    try:
        proc = subprocess.run(["mpirun", "-n", "16", "superlattice_builder", xml_file], 
                            capture_output=True, text=True, cwd=project_dir)
    except Exception as e:
        raise RuntimeError(f"Ошибка запуска subprocess: {e}")

    # Проверяем код возврата
    if proc.returncode != 0:
        print("[ERROR] superlattice_builder завершился с ошибкой")
        print("stdout:\n", proc.stdout)
        print("stderr:\n", proc.stderr)
        raise RuntimeError(f"superlattice_builder вернул код {proc.returncode}")

    # Ищем имя созданного файла в выводе
    match = re.search(r"Target filename:\s*\S+(superlattice_\S+)_24_24_24\.h5", proc.stdout)
    if not match:
        # Альтернативный поиск
        match = re.search(r"(superlattice_\S+)_24_24_24\.h5", proc.stdout)
    
    if match:
        stem = match.group(1)
        print("[INFO] Суперрешетка построена, основая часть имени файла:", stem)
        return stem
    else:
        print("Полный вывод superlattice_builder:")
        print(proc.stdout)
        raise RuntimeError("Не удалось найти имя .h5 в выводе superlattice_builder")

def compute_kappa(stem: str, R: float, x1: int, x2: int, temp: int) -> pd.DataFrame:
    """Запуск kappa_crossplanefilms для данного stem и температуры.
       Возвращает DataFrame с результатами и добавленными параметрами."""
    
    xml_content = f'''<crossplanefilmsweep>
  <H5repository root_directory="."/>
  <compound directory="./AlN_GaN" base="{stem}" gridA="24" gridB="24" gridC="24"/>
  <sweep type="log" start="1e-9" stop="1e-4" points="51"/>
  <temperature K="{temp}"/>
  <transportAxis x="0" y="0" z="1"/>
  <target directory="result" file="AUTO"/>
</crossplanefilmsweep>
'''
    xml_file = os.path.join(project_dir, f"{stem}_T{temp}.xml")
    with open(xml_file, "w") as f:
        f.write(xml_content)

    # Создаем директорию result если её нет
    os.makedirs(os.path.join(project_dir, "result"), exist_ok=True)

    try:
        proc = subprocess.run(["kappa_crossplanefilms", xml_file], 
                            capture_output=True, text=True, cwd=project_dir)
    except Exception as e:
        raise RuntimeError(f"Ошибка запуска kappa_crossplanefilms: {e}")
    
    # Ищем имя созданного CSV файла
    match = re.search(r"Writing film conductivities to file\s+(\S+\.crossplanefilms)", proc.stdout)
    if not match:
        match = re.search(r"(\S+\.crossplanefilms)", proc.stdout)
    
    if match:
        csv_filename = match.group(1)
        csv_path = os.path.join(project_dir, "result", csv_filename)
        print("[INFO] Подсчет теплопроводности завершен, результаты в:", csv_path)
        
        # Читаем результаты
        df = pd.read_csv(csv_path)
        df = df.iloc[:, :2]  # первые два столбца
        df.columns = ["thickness", "crossplane"]
        df["r"] = R
        df["x"] = x1
        df["y"] = x2
        df["t"] = temp
        return df
    else:
        print("Полный вывод kappa_crossplanefilms:")
        print(proc.stdout)
        raise RuntimeError("Не удалось найти имя .crossplanefilms в выводе kappa_crossplanefilms")

def data_generator(R_values, layer_counts, temperatures):
    """Генератор данных с различными сочетаниями параметров"""
    results = []
    total_combinations = len(R_values) * len(layer_counts) * len(layer_counts) * len(temperatures)
    current_combination = 0

    for R in R_values:
        for x1, x2 in product(layer_counts, repeat=2):
            current_combination += 1
            print(f"\n[PROGRESS] Обрабатывается комбинация {current_combination}/{total_combinations}: R={R}, x1={x1}, x2={x2}")
            
            try:
                stem = build_superlattice(R, x1, x2)
            except Exception as e:
                print(f"[ERROR] Ошибка в superlattice R={R}, x1={x1}, x2={x2}: {e}")
                continue  # Продолжаем со следующей комбинацией

            for temp in temperatures:
                try:
                    df = compute_kappa(stem, R, x1, x2, temp)
                    results.append(df)
                    print(f"[SUCCESS] Успешно обработано: R={R}, x1={x1}, x2={x2}, T={temp}K")
                except Exception as e:
                    print(f"[ERROR] Ошибка в kappa R={R}, x1={x1}, x2={x2}, T={temp}: {e}")
                    continue

    if results:
        final_df = pd.concat(results, ignore_index=True)
        final_df.to_csv("dataset.csv", index=False)
        print(f"\n[DONE] Сохранён dataset.csv с {len(final_df)} записями")
        print("Структура данных:")
        print(final_df.head())
        print(f"\nУникальные комбинации параметров:")
        print(f"R: {final_df['r'].unique()}")
        print(f"x1: {final_df['x'].unique()}")
        print(f"x2: {final_df['y'].unique()}")
        print(f"T: {final_df['t'].unique()}")
    else:
        print("[ERROR] Не удалось получить ни одной записи")

# Параметры для перебора
R_values = [0.0, 0.1, 0.3, 0.5, 0.7, 0.9]
layer_counts = [2, 5, 10, 20]  # x1 и x2 будут браться отсюда
temperatures = [300, 400, 500]

# Запуск генерации данных
data_generator(R_values, layer_counts, temperatures)