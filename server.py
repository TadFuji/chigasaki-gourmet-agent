"""
MCPサーバー: Google Maps Places APIをラップして、
茅ヶ崎のグルメ検索用のツールを提供します。

このサーバーは、MCP（Model Context Protocol）の標準に従って実装されています。
クライアントは、このサーバーに接続してsearch_placesツールを呼び出すことができます。
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Sequence
from dotenv import load_dotenv
import httpx

# 現在のスクリプトのディレクトリを取得
SCRIPT_DIR = Path(__file__).parent
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)

# 環境変数を読み込む（.envファイルから）
# スクリプトのディレクトリで.envファイルを探す
env_path = SCRIPT_DIR / ".env"
load_dotenv(dotenv_path=env_path)

# Google Maps APIキー（後で初期化）
# サーバー起動時ではなく、ツールが呼ばれたときに読み込みます
# これにより、サーバーが正常に起動できるようになります
MAPS_API_KEY = None

# MCPサーバーインスタンスを作成
# サーバー名は「chigasaki-gourmet-server」とします
server = Server("chigasaki-gourmet-server")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """
    この関数は、サーバーが提供するツールのリストを返します。
    クライアントは、この関数を呼び出して利用可能なツールを確認できます。
    
    MCPのlist_tools()コールバックとして登録されています。
    """
    return [
        Tool(
            name="search_places",
            description=(
                "茅ヶ崎市内のレストランやグルメスポットを検索します。"
                "Google Maps Places APIのテキスト検索を使用して、"
                "指定されたクエリに一致する場所を検索します。"
                "評価が4.0以上の場所のみを返します。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "検索クエリ（例: '茅ヶ崎 ランチ', 'Delicious lunch spots in Chigasaki City'）",
                    },
                    "min_rating": {
                        "type": "number",
                        "description": "最小評価（デフォルト: 4.0）",
                        "default": 4.0,
                    },
                },
                "required": ["query"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
    """
    ツール呼び出しを処理する関数。
    クライアントがツールを呼び出すと、この関数が実行されます。
    
    MCPのcall_tool()コールバックとして登録されています。
    
    Args:
        name: 呼び出されるツールの名前
        arguments: ツールに渡される引数（JSON形式）
    
    Returns:
        TextContentまたはその他のコンテンツタイプのシーケンス
    """
    if name == "search_places":
        return await handle_search_places(arguments)
    else:
        raise ValueError(f"未知のツール: {name}")


async def handle_search_places(arguments: dict[str, Any]) -> Sequence[TextContent]:
    """
    search_placesツールの実際の処理を行う関数。
    Google Maps Places API (New)を使用して場所を検索し、
    評価が指定値以上の場所のみをフィルタリングして返します。
    
    Args:
        arguments: {
            "query": 検索クエリ文字列,
            "min_rating": 最小評価（オプション、デフォルト4.0）
        }
    
    Returns:
        TextContentのリスト（JSON形式の検索結果を含む）
    """
    global MAPS_API_KEY
    
    # Google Maps APIキーを読み込み（初回のみ）
    if MAPS_API_KEY is None:
        MAPS_API_KEY = os.getenv("MAPS_API_KEY")
        if not MAPS_API_KEY:
            error_message = "MAPS_API_KEY環境変数が設定されていません。.envファイルを確認してください。"
            return [TextContent(type="text", text=json.dumps({"error": error_message}, ensure_ascii=False))]
    
    query = arguments.get("query", "")
    min_rating = arguments.get("min_rating", 4.0)
    
    if not query:
        raise ValueError("検索クエリが指定されていません。")
    
    try:
        # Google Maps Places API (New)のテキスト検索を実行
        # 「茅ヶ崎」を含むクエリとして処理し、場所を検索します
        # クエリに「茅ヶ崎」が含まれていない場合は、自動的に追加します
        search_query = query
        if "茅ヶ崎" not in query and "Chigasaki" not in query:
            search_query = f"茅ヶ崎 {query}"
        
        # Places API (New) Text Searchを実行
        # 新しいAPIエンドポイント: https://places.googleapis.com/v1/places:searchText
        url = "https://places.googleapis.com/v1/places:searchText"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": MAPS_API_KEY,
            "X-Goog-FieldMask": "places.id,places.displayName,places.rating,places.userRatingCount,places.formattedAddress,places.types,places.location"
        }
        payload = {
            "textQuery": search_query,
            "languageCode": "ja"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=30.0)
            response.raise_for_status()
            places_result = response.json()
        
        # 結果を処理
        places = []
        if "places" in places_result:
            for place in places_result["places"]:
                rating = place.get("rating", 0)
                
                # 評価が最小値以上の場所のみを追加
                if rating >= min_rating:
                    display_name = place.get("displayName", {})
                    name = display_name.get("text", "不明") if isinstance(display_name, dict) else str(display_name)
                    
                    formatted_address = place.get("formattedAddress", "住所不明")
                    location = place.get("location", {})
                    
                    place_info = {
                        "name": name,
                        "rating": rating,
                        "user_ratings_total": place.get("userRatingCount", 0),
                        "address": formatted_address,
                        "place_id": place.get("id", ""),
                        "types": place.get("types", []),
                        "geometry": {"location": location} if location else {},
                    }
                    places.append(place_info)
        
        # 結果をJSON文字列としてフォーマット
        result_json = json.dumps(
            {
                "query": query,
                "min_rating": min_rating,
                "count": len(places),
                "places": places,
            },
            ensure_ascii=False,
            indent=2,
        )
        
        return [TextContent(type="text", text=result_json)]
        
    except httpx.HTTPStatusError as e:
        # HTTPステータスエラーのハンドリング
        error_message = f"API呼び出しエラー (ステータス {e.response.status_code}): {e.response.text}"
        return [TextContent(type="text", text=json.dumps({"error": error_message}, ensure_ascii=False))]
    except Exception as e:
        # エラーハンドリング: APIキーが無効、クォータ超過、ネットワークエラーなど
        error_message = f"検索中にエラーが発生しました: {str(e)}"
        return [TextContent(type="text", text=json.dumps({"error": error_message}, ensure_ascii=False))]


async def main():
    """
    メイン関数: MCPサーバーを起動します。
    stdio_serverを使用して標準入出力を通じてクライアントと通信します。
    """
    # サーバーの初期化オプションを設定
    # Server.create_initialization_options()を使用して初期化オプションを作成します
    init_options = server.create_initialization_options(
        notification_options=None,
        experimental_capabilities=None,
    )
    # stdioサーバーを起動（標準入出力を使用）
    # これにより、クライアントは子プロセスとしてこのサーバーを起動できます
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            init_options,
        )


if __name__ == "__main__":
    # サーバーを起動
    asyncio.run(main())
