FROM apache/spark:3.5.3-scala2.12-java17-python3-ubuntu

USER root

RUN pip install --no-cache-dir requests

RUN mkdir -p /opt/spark-extra-jars && \
    curl -L -o /opt/spark-extra-jars/spark-sql-kafka.jar \
      "https://repo1.maven.org/maven2/org/apache/spark/spark-sql-kafka-0-10_2.12/3.5.3/spark-sql-kafka-0-10_2.12-3.5.3.jar" && \
    curl -L -o /opt/spark-extra-jars/kafka-clients.jar \
      "https://repo1.maven.org/maven2/org/apache/kafka/kafka-clients/3.5.1/kafka-clients-3.5.1.jar" && \
    curl -L -o /opt/spark-extra-jars/spark-token-provider.jar \
      "https://repo1.maven.org/maven2/org/apache/spark/spark-token-provider-kafka-0-10_2.12/3.5.3/spark-token-provider-kafka-0-10_2.12-3.5.3.jar" && \
    curl -L -o /opt/spark-extra-jars/commons-pool2.jar \
      "https://repo1.maven.org/maven2/org/apache/commons/commons-pool2/2.12.0/commons-pool2-2.12.0.jar" && \
    curl -L -o /opt/spark-extra-jars/spark-cassandra-connector-assembly.jar \
      "https://repo1.maven.org/maven2/com/datastax/spark/spark-cassandra-connector-assembly_2.12/3.5.0/spark-cassandra-connector-assembly_2.12-3.5.0.jar"

COPY processor.py /app/processor.py

CMD ["/opt/spark/bin/spark-submit", \
     "--master", "local[*]", \
     "--jars", "/opt/spark-extra-jars/spark-sql-kafka.jar,/opt/spark-extra-jars/kafka-clients.jar,/opt/spark-extra-jars/spark-token-provider.jar,/opt/spark-extra-jars/commons-pool2.jar,/opt/spark-extra-jars/spark-cassandra-connector-assembly.jar", \
     "--conf", "spark.cassandra.connection.host=cassandra", \
     "--conf", "spark.driver.extraClassPath=/opt/spark-extra-jars/*", \
     "/app/processor.py"]
