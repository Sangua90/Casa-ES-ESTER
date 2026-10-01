"""Authenticated multipart upload into the local, non-executable teaching pipeline."""
from __future__ import annotations

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.http import KEY_HASS

from .knowledge_files import prepare_documents, document_collection


class KnowledgeUploadView(HomeAssistantView):
    url = "/api/ester/knowledge/upload"
    name = "api:ester:knowledge:upload"
    requires_auth = True

    def runtime(self, request):
        entries = [e for e in request.app[KEY_HASS].config_entries.async_entries("ester")
                   if getattr(e, "runtime_data", None) is not None and e.state.value == "loaded"]
        return entries[0].runtime_data if entries else None

    async def get(self, request):
        if not request["hass_user"].is_admin:
            return self.json({"error": "Solo gli amministratori possono vedere i file."}, status_code=403)
        runtime = self.runtime(request)
        if runtime is None:
            return self.json({"error": "E.S.T.E.R. non è caricato."}, status_code=503)
        async with runtime.storage.lock:
            return self.json(document_collection(runtime.storage.data))

    async def post(self, request):
        user = request["hass_user"]
        if not user.is_admin:
            return self.json({"error": "Solo gli amministratori possono caricare conoscenze."}, status_code=403)
        try:
            reader = await request.multipart()
            files = []
            total = 0
            while part := await reader.next():
                if part.name != "files" or not part.filename or len(files) >= 5:
                    raise ValueError("Scegli da uno a cinque file nel campo files.")
                content = bytearray()
                while chunk := await part.read_chunk():
                    total += len(chunk)
                    content.extend(chunk)
                    if len(content) > 32000 or total > 64000:
                        raise ValueError("Limite: 32 KB per file, 64 KB complessivi.")
                files.append({"name": part.filename, "content": content.decode("utf-8-sig")})
            runtime = self.runtime(request)
            if runtime is None:
                return self.json({"error": "E.S.T.E.R. non è caricato."}, status_code=503)
            result = await prepare_documents(runtime, files)
            return self.json({"proposal": result, "collection": document_collection(runtime.storage.data), "uploaded_files": [
                {"name": f["name"], "size": len(f["content"].encode("utf-8"))} for f in files
            ]})
        except UnicodeDecodeError:
            return self.json({"error": "I file devono contenere testo UTF-8."}, status_code=400)
        except (ValueError, TypeError, AssertionError, HomeAssistantError) as err:
            return self.json({"error": str(err)}, status_code=400)
        except web.HTTPRequestEntityTooLarge:
            return self.json({"error": "File troppo grandi."}, status_code=413)
        except OSError:
            return self.json({"error": "Salvataggio non riuscito. Controlla lo spazio disponibile e riprova."}, status_code=500)
