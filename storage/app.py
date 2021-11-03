import connexion
from connexion import NoContent
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from base import Base
from customer_orders import CustomerOrder
from completed_orders import CompletedOrder
import yaml
import logging.config
from datetime import datetime
from pykafka import KafkaClient
from pykafka.common import OffsetType
from threading import Thread

with open("app_conf.yml", 'r') as f:
    app_config = yaml.safe_load(f.read())
    db_info = app_config["datastore"]
    kafka_info = app_config["events"]

with open("log_conf.yml", "r") as f:
    log_config = yaml.safe_load(f.read())
    logging.config.dictConfig(log_config)
    logger = logging.getLogger("basicLogger")

DB_ENGINE = create_engine("mysql+pymysql://%s:%s@%s:%s/%s"
                          % (db_info["user"], db_info["password"], db_info["hostname"], db_info["port"], db_info["db"]))
Base.metadata.bind = DB_ENGINE
DB_SESSION = sessionmaker(bind=DB_ENGINE)


def get_customer_order_readings(timestamp):

    session = DB_SESSION()

    timestamp_datetime = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S%fZ")

    readings = session.query(CustomerOrder).filter(CustomerOrder.date_created >=
                                                   timestamp_datetime)

    results_list = []

    for reading in readings:
        results_list.append(reading.to_dict())

    session.close()

    logger.info("Query for Customer order readings after %s returns %d results" % (timestamp, len(results_list)))

    return results_list, 200


def get_completed_order_readings(timestamp):

    session = DB_SESSION()

    timestamp_datetime = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")

    readings = session.query(CompletedOrder).filter(CompletedOrder.date_created >=
                                                    timestamp_datetime)

    results_list = []

    for reading in readings:
        results_list.append(reading.to_dict())

    session.close()

    logger.info("Query for Completed order readings after %s returns %d results" % (timestamp, len(results_list)))

    return results_list, 200


def customer_orders_reading(body):
    session = DB_SESSION()

    cust_order = CustomerOrder(
        body['order_id'],
        body['device_id'],
        body['releaseDate'],
        body['product']['num_of_prduct'],
        body['product']['product_name'])

    session.add(cust_order)

    session.commit()
    session.close()

    logger.info("Connecting to DB.Hostname: %s, Port: %s" % (db_info["hostname"], db_info["port"]))

    return NoContent, 201


def completed_orders_reading(body):
    session = DB_SESSION()

    comp_order = CompletedOrder(
        body['order_id'],
        body['completedDate'],
        body['device_id'],
        body['status'])

    session.add(comp_order)

    session.commit()
    session.close()

    logger.info("Connecting to DB.Hostname: %s, Port: %s" % (db_info["hostname"], db_info["port"]))

    return NoContent, 201


def process_messages():
    """ Process event messages """
    hostname = "%s:%d" % (kafka_info["hostname"], kafka_info["port"])
    client = KafkaClient(hosts=hostname)
    topic = client.topics[str.encode(kafka_info["topic"])]

    consumer = topic.get_simple_consumer(consumer_group=b'event_group',
                                          reset_offset_on_start=False,
                                          auto_offset_reset=OffsetType.LATEST)

    for msg in consumer:
        msg_str = msg.value.decode('utf-8')
        msg = json.loads(msg_str)
        logger.info("Message: %s" % msg)

        payload = msg["payload"]

        if msg["type"] == "customer_orders":
            cust_order = CustomerOrder(
                payload['order_id'],
                payload['device_id'],
                payload['releaseDate'],
                payload['product']['num_of_prduct'],
                payload['product']['product_name'])
            return cust_order

        elif msg["type"] == "completed_orders":
            comp_order = CompletedOrder(
                payload['order_id'],
                payload['completedDate'],
                payload['device_id'],
                payload['status'])
            return comp_order

        consumer.commit_offsets()


app = connexion.FlaskApp(__name__, specification_dir='')
app.add_api("dcheng-Lab05.yaml", strict_validation=True, validate_responses=True)

if __name__ == "__main__":
    app.run(port=8090)
    t1 = Thread(target=process_messages)
    t1.setDaemon(True)
    t1.start()