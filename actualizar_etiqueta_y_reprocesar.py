"""
Script para actualizar la anotación de 'buenos_validacion_frontal_arabica'
desde el JSON de Label Studio y regenerar los datasets y zips.
"""

import json
import os
import zipfile
from src.configuracion import Configuracion
from src.gestor_dataset import GestorDataset

# Mapeo de nombres a IDs
MAPEO_CLASES = {
    "Arabica_Agrio": 0,
    "Arabica_Brocado": 1,
    "Arabica_Bueno": 2,
    "Arabica_Cereza": 3,
    "Arabica_Concha": 4,
    "Arabica_Inmaduro": 5,
    "Arabica_Negro": 6,
    "Arabica_Quebrado": 7,
    "Robusta_Brocado": 8,
    "Robusta_Bueno": 9,
    "Robusta_Cereza": 10,
    "Robusta_Negro": 11,
    "Robusta_Quebrado": 12,
}

JSON_RAW = '''{
  "id": 47,
  "data": {
    "image": "/data/upload/3/6360bd39-buenos_validacion_frontal_arabica.jpg"
  },
  "annotations": [
    {
      "id": 13,
      "result": [
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 0.6755184227897789,
            "y": 1.2009216405151624,
            "width": 1.7604419503006357,
            "height": 4.548945608011978,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "CSxJ-fBR-J",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 1.2282153141632344,
            "y": 10.589945375451885,
            "width": 2.0265552683693366,
            "height": 3.6391564864095827,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "FamqbDFOK3",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 2.026553464690191,
            "y": 15.357240372648462,
            "width": 2.3540811558253547,
            "height": 4.548945608011954,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "_ixIK9mP1d",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 2.8044222618206676,
            "y": 19.323920942834892,
            "width": 2.12890925006833,
            "height": 2.9477167539917586,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "72qcDPP5Iv",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 0,
            "y": 29.513559104781717,
            "width": 1.5352691427040428,
            "height": 3.639156486409579,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Quebrado"
            ]
          },
          "id": "F55DiySqAZ",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 0,
            "y": 23.181426818429042,
            "width": 1.5966799084122045,
            "height": 3.529981791817299,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "IgSIqFC7m5",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 0.4708158704292408,
            "y": 25.14657132109023,
            "width": 2.2926718931831362,
            "height": 5.276776905293875,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "_OM8cbDTbO",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 0.08187951787826094,
            "y": 20.015360675252705,
            "width": 2.865837236113502,
            "height": 4.4033793485556565,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "m8Oe4aPdsf",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 1.7604419503006354,
            "y": 0.4366987783691499,
            "width": 1.944674247425121,
            "height": 4.366987783691499,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "35KX_8_18u",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 0,
            "y": 14.17678868932663,
            "width": 1.3122502188696328,
            "height": 3.5890604276776283,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "B7-eDAGjsA",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 0,
            "y": 17.94530213838814,
            "width": 1.716019516983366,
            "height": 2.1534362566065752,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "E2UhHPNU-K",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 0,
            "y": 27.407277064458018,
            "width": 0.5785923452967408,
            "height": 1.903400080811773,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "iKLzIsJtEr",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 8.326672684688674e-17,
            "y": 8.80713148183841,
            "width": 1.1879517273015452,
            "height": 4.3136970523290135,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "UyrfnJXrVL",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 0.05055113733198064,
            "y": 6.56041426708371,
            "width": 1.187951727301545,
            "height": 2.65112631341054,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "cNxFIPCqwZ",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 0.05055113733198064,
            "y": 5.167449593935798,
            "width": 0.960471609307632,
            "height": 2.1119141818694134,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "yBwsJJuDCk",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 0,
            "y": 1.797373771803756,
            "width": 0.6824403539817386,
            "height": 3.23527278924676,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Quebrado"
            ]
          },
          "id": "wq8riz42Sa",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 0,
            "y": 0,
            "width": 1.8450853334151793,
            "height": 1.6625707389184743,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Quebrado"
            ]
          },
          "id": "7HblB4mmwH",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 1.8708857447337925,
            "y": 0,
            "width": 1.9962606715616695,
            "height": 0.7189495087215023,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Quebrado"
            ]
          },
          "id": "lgyVMRygWe",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 60.383402772571635,
            "y": 53.629737321012094,
            "width": 2.6025023721026495,
            "height": 5.834142736949736,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "p4LZxmgFHM",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 57.50189325894816,
            "y": 65.97620568259573,
            "width": 3.1306134944324646,
            "height": 3.97538253592127,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "8pWHkKUWzS",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 66.10248350735208,
            "y": 64.72243119049763,
            "width": 2.1845458692809863,
            "height": 5.810174475577236,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Brocado"
            ]
          },
          "id": "Ypz94mWu4n",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 52.643720624375135,
            "y": 48.930480673769864,
            "width": 3.648828136853811,
            "height": 4.431584772640304,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Brocado"
            ]
          },
          "id": "bW5BQGghJk",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 51.90972608438214,
            "y": 40.45851998226025,
            "width": 2.7092758916692143,
            "height": 5.741256645101709,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "OlDtZb2xeJ",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 58.47701180066933,
            "y": 37.722753392983606,
            "width": 3.381175357922196,
            "height": 4.431171236152304,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "MFBKWfLCbV",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 42.936611015340695,
            "y": 37.6842214691909,
            "width": 2.6442465861022595,
            "height": 6.935746282673184,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "GAGz8NbEg8",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 42.91493012404037,
            "y": 50.476820168343764,
            "width": 2.7092758916692072,
            "height": 5.741256645101686,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "Qe5DdJaggB",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 46.88131002944411,
            "y": 54.8309275569108,
            "width": 2.5575564417357417,
            "height": 4.43117123615231,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "1spiebT4Jw",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 48.225114372942336,
            "y": 67.54646240847816,
            "width": 2.600901354772166,
            "height": 4.777958550285958,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "C5wgoHupYX",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 39.035252458162354,
            "y": 64.61803620023842,
            "width": 2.947686759143814,
            "height": 4.585298931322805,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "FcX3OSbWg3",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 38.536741874571234,
            "y": 74.59780446252941,
            "width": 2.4925322288673586,
            "height": 5.317405483382825,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "0MLPOd_gt5",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 50.240813408288574,
            "y": 78.91337992730386,
            "width": 2.535880961427722,
            "height": 3.699064684092341,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "bZxp4WGMPQ",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 36.542965801799745,
            "y": 52.42845977834164,
            "width": 2.3825226588681843,
            "height": 4.89244487813442,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "uCYIxFP0Rm",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 38.092210885941455,
            "y": 43.86937310798466,
            "width": 1.8304633385607953,
            "height": 4.366341360982501,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "-XxnZir3SH",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 61.521509225761996,
            "y": 43.2287287047999,
            "width": 3.4660005197612516,
            "height": 4.525056234132699,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "tZXWET5BLo",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 66.88297877976765,
            "y": 48.812840653304114,
            "width": 2.4641097445177547,
            "height": 5.054584091318409,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "aG27yYxWZZ",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 70.43022402566899,
            "y": 40.48481162665548,
            "width": 3.1139745030147767,
            "height": 4.525056234132741,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "9anXwdzTqT",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 63.98562413975885,
            "y": 34.9969774703669,
            "width": 2.518260833159922,
            "height": 6.017362013474369,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "aI-kdPZFyu",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 68.5347446524664,
            "y": 28.305670911383462,
            "width": 2.1933284539113926,
            "height": 4.765750714671707,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "3F4KcPP4yq",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 60.8174778701855,
            "y": 25.080364872161198,
            "width": 2.3828745620313834,
            "height": 5.150861883534058,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "eJgMqY798f",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 54.12919271708031,
            "y": 24.454559222759855,
            "width": 3.0598158589801683,
            "height": 4.862028506887298,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "u7vZHsQCCL",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 47.657508339673704,
            "y": 27.920559742521107,
            "width": 2.6536554549854885,
            "height": 6.209917597905544,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "97oTF0hjq8",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 36.42008915368496,
            "y": 20.362753053597288,
            "width": 1.7871509508705887,
            "height": 3.321583831437879,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "zbOcYxi3cT",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 33.81518688828027,
            "y": 31.57279910625806,
            "width": 2.5338950373193487,
            "height": 5.06280995769544,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "kD1uceST-L",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 58.770965138145485,
            "y": 78.25199635316068,
            "width": 2.7787109040210987,
            "height": 5.81425447763725,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "jEaE-RKTQN",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 67.205461825968,
            "y": 75.41044341296212,
            "width": 2.6311662042968664,
            "height": 4.153038912597857,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "avapslqU-V",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 70.96922619444169,
            "y": 67.35508312199208,
            "width": 2.4120518856285105,
            "height": 3.9134035068516932,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "o830yAziiZ",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 70.87884795470006,
            "y": 54.08300729662143,
            "width": 2.5854380071623044,
            "height": 4.5803198361960344,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "NFjDdNrhlu",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 73.10394254269661,
            "y": 49.518702564747905,
            "width": 3.129352450661533,
            "height": 5.36505994799183,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "h8LyqQvvei",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 76.04799394943133,
            "y": 39.868745845089244,
            "width": 2.580468451021946,
            "height": 3.967579968250824,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "clDV2j6oC0",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 40.207722298819434,
            "y": 10.076097485031093,
            "width": 2.102557418417652,
            "height": 4.1050767531608185,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "zkKoGjxDEy",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 49.715452468346186,
            "y": 14.89724289664399,
            "width": 1.9962924321429671,
            "height": 4.905911947663423,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "qQ_Umo5AyM",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 57.81016538865662,
            "y": 11.252283148045047,
            "width": 2.1841796287668123,
            "height": 5.949723000357755,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "epYuGzD9fL",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 64.11609632602786,
            "y": 13.005885716571534,
            "width": 2.430772574684271,
            "height": 4.9685406108250865,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "b3OYxvyfJl",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 72.27738709634542,
            "y": 17.87004522212716,
            "width": 2.9357230693615035,
            "height": 5.198179042417831,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "kOOTUD4vJq",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        },
        {
          "original_width": 1920,
          "original_height": 1080,
          "image_rotation": 0,
          "value": {
            "x": 73.5103949380349,
            "y": 10.145843432189023,
            "width": 2.6538880494397614,
            "height": 4.676273516070665,
            "rotation": 0,
            "rectanglelabels": [
              "Arabica_Bueno"
            ]
          },
          "id": "yLSxrsnkFd",
          "from_name": "label",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual"
        }
      ]
    }
  ]
}'''


def convertir_y_guardar_etiqueta():
    data = json.loads(JSON_RAW)
    results = data["annotations"][0]["result"]
    print(f"[*] Total de anotaciones encontradas en JSON: {len(results)}")
    
    lineas_yolo = []
    for r in results:
        val = r["value"]
        x_pct = float(val["x"])
        y_pct = float(val["y"])
        w_pct = float(val["width"])
        h_pct = float(val["height"])
        
        # Calcular centro y dimensiones normalizadas en rango [0, 1]
        x_center = (x_pct + w_pct / 2.0) / 100.0
        y_center = (y_pct + h_pct / 2.0) / 100.0
        w = w_pct / 100.0
        h = h_pct / 100.0
        
        clase_str = val["rectanglelabels"][0]
        clase_id = MAPEO_CLASES.get(clase_str, 2)  # Por defecto 2 (Arabica_Bueno)
        
        lineas_yolo.append(f"{clase_id} {x_center:.6f} {y_center:.6f} {w:.6f} {h:.6f}")
        
    ruta_txt = "dataset_bruto/labels/buenos_validacion_frontal_arabica.txt"
    with open(ruta_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas_yolo) + "\n")
        
    print(f"[OK] Archivo '{ruta_txt}' actualizado con éxito ({len(lineas_yolo)} etiquetas).")


def regenerar_dataset_yolo():
    print("\n" + "=" * 60)
    print("  REGENERANDO DATASET YOLO (640x640)")
    print("=" * 60)
    
    config = Configuracion(
        directorio_imagenes_entrada="dataset_bruto/images",
        directorio_etiquetas_entrada="dataset_bruto/labels",
        directorio_salida="dataset_yolo",
        tamano_objetivo=640,
        proporcion_division=(0.8, 0.1, 0.1),
        semilla_aleatoria=42,
    )
    
    gestor = GestorDataset(config)
    gestor.ejecutar_pipeline()
    
    # Comprimir dataset_yolo.zip
    archivo_zip = "dataset_yolo.zip"
    print(f"\n[*] Comprimiendo '{config.directorio_salida}' en '{archivo_zip}'...")
    with zipfile.ZipFile(archivo_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        for raiz, _, archivos in os.walk(config.directorio_salida):
            for archivo in archivos:
                ruta_completa = os.path.join(raiz, archivo)
                ruta_relativa = os.path.relpath(ruta_completa, os.path.dirname(config.directorio_salida))
                zipf.write(ruta_completa, ruta_relativa)
                
    tamano_mb = os.path.getsize(archivo_zip) / (1024 * 1024)
    print(f"[OK] Archivo '{archivo_zip}' actualizado ({tamano_mb:.2f} MB).")


def main():
    convertir_y_guardar_etiqueta()
    regenerar_dataset_yolo()


if __name__ == "__main__":
    main()
