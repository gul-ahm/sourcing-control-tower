FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Build the warehouse at image build time so the container starts with data.
RUN python fetch.py --offline && python load.py && dbt build --profiles-dir . --full-refresh

EXPOSE 8501
CMD ["streamlit", "run", "dashboard/app.py", "--server.address", "0.0.0.0"]
