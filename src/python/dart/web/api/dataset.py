import json

from flask import Blueprint, request, current_app
from flask.ext.jsontools import jsonapi


from dart.model.dataset import Dataset
from dart.service.dataset import DatasetService
from dart.service.filter import FilterService
from dart.web.api.entity_lookup import fetch_model, accounting_track, check_login
from dart.util.dataset_guess import infer_dataset_data

api_dataset_bp = Blueprint('api_dataset', __name__)


@api_dataset_bp.route('/dataset', methods=['POST'])
@accounting_track
@jsonapi
@check_login
def post_dataset():
    return {'results': dataset_service().save_dataset(Dataset.from_dict(request.get_json())).to_dict()}


@api_dataset_bp.route('/dataset/<dataset>', methods=['GET'])
@fetch_model
@jsonapi
@check_login
def get_dataset(dataset):
    return {'results': dataset.to_dict()}


@api_dataset_bp.route('/dataset/guess', methods=['GET'])
@jsonapi
def get_dataset_guess():
    s3_path = request.args.get('s3_path')
    max_lines = int(request.args.get('max_lines'))
    best_guess_dataset = infer_dataset_data(s3_path, max_lines)
    return {'results': best_guess_dataset.to_dict()}


@api_dataset_bp.route('/dataset', methods=['GET'])
@jsonapi
@check_login
def find_datasets():
    limit = int(request.args.get('limit', 20))
    offset = int(request.args.get('offset', 0))
    filters = [filter_service().from_string(f) for f in json.loads(request.args.get('filters', '[]'))]
    datasets = dataset_service().query_datasets(filters, limit, offset)
    return {
        'results': [d.to_dict() for d in datasets],
        'limit': limit,
        'offset': offset,
        'total': dataset_service().query_datasets_count(filters)
    }


@api_dataset_bp.route('/dataset/<dataset>', methods=['PUT'])
@accounting_track
@fetch_model
@jsonapi
@check_login
def put_dataset(dataset):
    return {'results': dataset_service().update_dataset(dataset.id, Dataset.from_dict(request.get_json())).to_dict()}


@api_dataset_bp.route('/dataset/<dataset>', methods=['DELETE'])
@fetch_model
@accounting_track
@jsonapi
@check_login
def delete_dataset(dataset):
    dataset_service().delete_dataset(dataset.id)
    return {'results': 'OK'}


def filter_service():
    """ :rtype: dart.service.filter.FilterService """
    return current_app.dart_context.get(FilterService)


def dataset_service():
    """ :rtype: dart.service.dataset.DatasetService """
    return current_app.dart_context.get(DatasetService)
