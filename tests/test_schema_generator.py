import json
from collections import OrderedDict

import pytest
from rest_framework import routers, serializers, viewsets
from rest_framework.response import Response

from drf_yasg import codecs, openapi
from drf_yasg.codecs import yaml_sane_load
from drf_yasg.errors import SwaggerGenerationError
from drf_yasg.generators import OpenAPISchemaGenerator
from drf_yasg.utils import swagger_auto_schema


def test_schema_is_valid(swagger, codec_yaml):
    codec_yaml.encode(swagger)


def test_invalid_schema_fails(codec_json, mock_schema_request):
    # noinspection PyTypeChecker
    bad_generator = OpenAPISchemaGenerator(
        info=openapi.Info(
            title="Test generator", default_version="v1",
            contact=openapi.Contact(name=69, email=[])
        ),
        version="v2",
    )

    swagger = bad_generator.get_schema(mock_schema_request, True)
    with pytest.raises(codecs.SwaggerValidationError):
        codec_json.encode(swagger)


def test_json_codec_roundtrip(codec_json, swagger, validate_schema):
    json_bytes = codec_json.encode(swagger)
    validate_schema(json.loads(json_bytes.decode('utf-8')))


def test_yaml_codec_roundtrip(codec_yaml, swagger, validate_schema):
    yaml_bytes = codec_yaml.encode(swagger)
    assert b'omap' not in yaml_bytes  # ensure no ugly !!omap is outputted
    assert b'&id' not in yaml_bytes and b'*id' not in yaml_bytes  # ensure no YAML references are generated
    validate_schema(yaml_sane_load(yaml_bytes.decode('utf-8')))


def test_yaml_and_json_match(codec_yaml, codec_json, swagger):
    yaml_schema = yaml_sane_load(codec_yaml.encode(swagger).decode('utf-8'))
    json_schema = json.loads(codec_json.encode(swagger).decode('utf-8'), object_pairs_hook=OrderedDict)
    assert yaml_schema == json_schema


def test_basepath_only(mock_schema_request):
    with pytest.raises(SwaggerGenerationError):
        generator = OpenAPISchemaGenerator(
            info=openapi.Info(title="Test generator", default_version="v1"),
            version="v2",
            url='/basepath/',
        )

        generator.get_schema(mock_schema_request, public=True)


def test_no_netloc(mock_schema_request):
    generator = OpenAPISchemaGenerator(
        info=openapi.Info(title="Test generator", default_version="v1"),
        version="v2",
        url='',
    )

    swagger = generator.get_schema(mock_schema_request, public=True)
    assert 'host' not in swagger and 'schemes' not in swagger
    assert swagger['info']['version'] == 'v2'


def test_securiy_requirements(swagger_settings, mock_schema_request):
    generator = OpenAPISchemaGenerator(
        info=openapi.Info(title="Test generator", default_version="v1"),
        version="v2",
        url='',
    )
    swagger_settings['SECURITY_REQUIREMENTS'] = []

    swagger = generator.get_schema(mock_schema_request, public=True)
    assert swagger['security'] == []


def test_replaced_serializer():
    class DetailSerializer(serializers.Serializer):
        detail = serializers.CharField()

    class DetailViewSet(viewsets.ViewSet):
        serializer_class = DetailSerializer

        @swagger_auto_schema(responses={404: openapi.Response("Not found or Not accessible", DetailSerializer)})
        def retrieve(self, request, pk=None):
            serializer = DetailSerializer({'detail': None})
            return Response(serializer.data)

    router = routers.DefaultRouter()
    router.register(r'details', DetailViewSet, base_name='details')

    generator = OpenAPISchemaGenerator(
        info=openapi.Info(title="Test generator", default_version="v1"),
        version="v2",
        url='',
        patterns=router.urls
    )

    for _ in range(3):
        swagger = generator.get_schema(None, True)
        assert 'Detail' in swagger['definitions']
        assert 'detail' in swagger['definitions']['Detail']['properties']
        responses = swagger['paths']['/details/{id}/']['get']['responses']
        assert '404' in responses
        assert responses['404']['schema']['$ref'] == "#/definitions/Detail"
