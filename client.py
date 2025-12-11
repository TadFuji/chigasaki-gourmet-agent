"""
MCPクライアント（エージェント）: 
指定された地域のグルメ検索エージェントとして動作します。

このクライアントは、MCPサーバーに接続し、
search_placesツールを呼び出してレストラン情報を取得し、
ユーザーフレンドリーな日本語形式で出力します。
"""

import asyncio
import argparse
import json
import os
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv

# 現在のスクリプトのディレクトリを取得
SCRIPT_DIR = Path(__file__).parent

# 環境変数を読み込む（.envファイルから）
# スクリプトのディレクトリで.envファイルを探す
env_path = SCRIPT_DIR / ".env"
load_dotenv(dotenv_path=env_path)


async def main():
    """
    メイン関数: MCPサーバーに接続し、グルメ検索を実行します。
    """
    # サーバーの起動パラメータを設定
    # server.pyをPythonで実行するように指定
    # サーバーファイルの絶対パスを使用して、確実に見つけられるようにします
    server_script = SCRIPT_DIR / "server.py"
    
    # 環境変数を現在のプロセスの環境変数から継承（.envファイルから読み込んだものも含む）
    server_params = StdioServerParameters(
        command="python",
        args=[str(server_script)],
        env=os.environ.copy(),  # 環境変数を明示的にコピー
    )
    
    # stdioクライアントを使用してサーバーに接続
    # サーバーは子プロセスとして起動され、標準入出力で通信します
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # サーバーを初期化
            # この呼び出しで、サーバーとクライアント間のプロトコルハンドシェイクが行われます
            await session.initialize()
            
            print("=" * 60)
            print("グルメ検索エージェント")
            print("=" * 60)
            print()
            
            # コマンドライン引数を解析
            parser = argparse.ArgumentParser(
                description="指定された地域のグルメスポットを検索します"
            )
            parser.add_argument(
                "location",
                nargs="?",
                default="茅ヶ崎市",
                help="検索する地域名（例: 茅ヶ崎市, 藤沢市, 平塚市, 寒川町, 新宿区）"
            )
            parser.add_argument(
                "-q", "--query",
                default="ランチ",
                help="検索クエリ（例: ランチ, ディナー, カフェ）"
            )
            parser.add_argument(
                "-r", "--min-rating",
                type=float,
                default=4.0,
                help="最小評価（デフォルト: 4.0）"
            )
            
            args = parser.parse_args()
            location = args.location
            query = args.query
            min_rating = args.min_rating
            
            print(f"📍 地域: {location}")
            print(f"🔍 検索クエリ: {query}")
            print(f"⭐ 最小評価: {min_rating}以上")
            print()
            
            try:
                # search_placesツールを呼び出す
                # ツール名と引数を指定して、サーバーにリクエストを送信します
                result = await session.call_tool(
                    "search_places",
                    arguments={
                        "location": location,
                        "query": query,
                        "min_rating": min_rating,
                    },
                )
                
                # 結果を解析
                # MCPの応答は、TextContentオブジェクトのリストとして返されます
                if result.content:
                    # 最初のコンテンツアイテムからテキストを取得
                    result_text = result.content[0].text
                    
                    # JSON文字列をパース
                    data = json.loads(result_text)
                    
                    # エラーチェック
                    if "error" in data:
                        print(f"❌ エラー: {data['error']}")
                        return
                    
                    # 結果をユーザーフレンドリーな形式で表示
                    location_name = data.get('location', '指定地域')
                    print(f"✅ 検索完了: {location_name}で{data['count']}件のスポットが見つかりました")
                    print()
                    print("-" * 60)
                    
                    places = data.get("places", [])
                    if not places:
                        print("😔 条件に一致するスポットが見つかりませんでした。")
                        print("検索条件を変更してお試しください。")
                    else:
                        # 各スポットの情報を表示
                        for idx, place in enumerate(places, 1):
                            name = place.get('name', '不明')
                            rating = place.get('rating', 0)
                            user_ratings_total = place.get('user_ratings_total', 0)
                            address = place.get('address', '住所不明')
                            
                            print(f"\n📍 {idx}. {name}")
                            print(f"   ⭐ 評価: {rating:.1f} ({user_ratings_total}件のレビュー)")
                            print(f"   📍 住所: {address}")
                            
                            # タイプ情報がある場合、主要なタイプを表示
                            types = place.get('types', [])
                            if types:
                                # 日本語で読みやすいタイプを抽出
                                restaurant_types = [
                                    t for t in types 
                                    if t in ['restaurant', 'food', 'meal_takeaway', 'cafe', 'bakery']
                                ]
                                if restaurant_types:
                                    print(f"   🍽️  タイプ: {', '.join(restaurant_types)}")
                            
                            print()
                    
                    print("-" * 60)
                    print()
                    print("💡 ヒント: より詳細な情報は、Google Mapsで検索してください。")
                    
                else:
                    print("❌ サーバーから結果が返されませんでした。")
                    
            except Exception as e:
                # エラーハンドリング: 接続エラー、ツール呼び出しエラーなど
                print(f"❌ エラーが発生しました: {str(e)}")
                print()
                print("トラブルシューティング:")
                print("1. .envファイルにMAPS_API_KEYが設定されているか確認してください")
                print("2. server.pyが正常に起動できるか確認してください")
                print("3. インターネット接続を確認してください")
                sys.exit(1)


if __name__ == "__main__":
    # クライアントを実行
    asyncio.run(main())
