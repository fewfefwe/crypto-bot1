import pandas as pd
import os
import joblib
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

# 📥 Загружаем размеченные данные
data_path = os.path.join(os.path.dirname(__file__), "labeled_market_data.csv")
df = pd.read_csv(data_path)

# 🎯 Определяем признаки и целевую переменную
X = df.drop(["label", "symbol"], axis=1)
y = df["label"]

# 🔁 Масштабируем данные
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# 🧪 Разделяем на обучающую и тестовую выборки
X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)

# 🤖 Обучаем нейросеть
model = MLPClassifier(hidden_layer_sizes=(64, 32), activation='relu', max_iter=500, random_state=42)
model.fit(X_train, y_train)

# 📊 Оцениваем точность
acc = model.score(X_test, y_test)
print(f"✅ Модель обучена! Точность на тесте: {acc:.2%}")

# 💾 Сохраняем модель и scaler
model_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "model"))
os.makedirs(model_dir, exist_ok=True)

joblib.dump(model, os.path.join(model_dir, "signal_model.pkl"))
joblib.dump(scaler, os.path.join(model_dir, "scaler.pkl"))

print("📁 Модель и scaler сохранены в папку /model")
