function getImportStatusFromStatusCode(status_code){
    if(status_code == 200)
        return 'Ready'
    else
        return 'Failed'
}


//                          bulletin_id, fileId, file_extension, etag, this.batch_id, getImportStatusFromStatusCode(response.status), "data", "log"
function getBulletinImportLog(bulletin_id, file, file_format, etag, batch_id, status, data, log){
    return {
        "table":"bulletin",
        "item_id":bulletin_id,
        "file":file,
        "file_format":file_format,
        "file_hash":etag,
        "batch_id":batch_id,
        "status":status,
        "data":data,
        "log":log
    }
}

function getMediaImportLog(media_id, file, file_format, etag, batch_id, status, data, log){
    return {
        "table":"media",
        "item_id":media_id,
        "file":file,
        "file_format":file_format,
        "file_hash":etag,
        "batch_id":batch_id,
        "status":status,
        "data":data,
        "log":log
    }
}