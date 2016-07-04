# Setup

1. Install ElasticSearch and run its instance:
  ```
  wget https://download.elastic.co/elasticsearch/release/org/elasticsearch/distribution/tar/elasticsearch/2.3.3/elasticsearch-2.3.3.tar.gz
  tar xzf elasticsearch-2.3.3.tar.gz
  ./elasticsearch-2.3.3/bin/elasticsearch
  ```

2. Install LogStash:
  ```
  wget https://download.elastic.co/logstash/logstash/logstash-2.3.3.tar.gz
  tar xzf logstash-2.3.3
  ```

3. Install JDBC plugin:
  ```
  ./logstash-2.3.3/bin/logstash-plugin install logstash-input-jdbc
  ```

4. Download JDBC driver for Postgres: https://jdbc.postgresql.org/download.html

5. Adjust `results-table.jsn` according to your setup.

# Usage

This command will import the results table into ElasticSearch index:

```sh
LS_HEAP_SIZE="2g" ./logstash-2.3.3/bin/logstash -f results-table.jsn
```

You can check that the items were indeed inserted:

```sh
curl -XPOST 'localhost:9200/annotation/_search?pretty' -d '
{
  "query": { "match_all": {} },
  "size": 1
}'
```
