const ready_import_status = 'Ready'
const skipped_import_status = 'Skipped'
const failed_import_status = 'Failed'
// https://support.clarivate.com/Endnote/s/article/EndNote-Directions-for-implementing-EndNote-Direct-Export?language=en_US

function getImportStatusFromStatusCode(status_code){
    if(status_code == 200)
        return ready_import_status
    else
        return failed_import_status
}

function getImportLog(zoteroItem, import_hash, batch_id, status, data, log){
    return {
        "table":"",
        "item_id":0,
        "file": getTitle(zoteroItem),
        "file_format":"",
        "file_hash":"",
        "import_hash": import_hash,
        "batch_id":batch_id,
        "status":status,
        "data":data,
        "log":log
    }
}

function getBulletinImportLog(bulletin_id, file, file_format, etag, import_hash, batch_id, status, data, log){
    return {
        "table":"primary record",
        "item_id":bulletin_id,
        "file":file,
        "file_format":file_format,
        "file_hash":etag,
        "import_hash": import_hash,
        "batch_id":batch_id,
        "status":status,
        "data":data,
        "log":log
    }
}

function getMediaImportLog(media_id, file, file_format, etag, import_hash, batch_id, status, data, log){
    log = {
        "table":"media",
        "item_id":media_id,
        "file":file,
        "file_format":file_format,
        "file_hash":etag,
        "import_hash": import_hash,
        "batch_id":batch_id,
        "status":status,
        "data":data,
        "log":log
    }
    return log
}

// this file contains functions to map between Zotero-exported RIS properties and CAESAR objects and contained properties
function isDateStringVariation1(dateString){
    return dateString.match(/[0-9]{4}[/][0-9]{2}[/][0-9]{2}[/][T][0-9]{2}[:][0-9]{2}[:][0-9]{2}[Z]/g)
}

function reformatDateStringVariation1(dateString){
    return dateString.substring(0, 10) + dateString.substring(11)
}

function reformatDatestring(dateString){
    parsedDate = new Date(dateString);
    reformattedString = parsedDate.toISOString()
    return reformattedString
}

function getPublishDate(zoteroItem){
    try{
        if("DA" in zoteroItem){
            dateString = zoteroItem["DA"]
            // dates from Zotero seem to come back in this very specific bad format YYYY/MM/DD/Thh:mm:ssZ (we need YYYY/MM/DDThh:mm:ssZ)
            // this method has a very specific resolution for this very specific issue
            if(isDateStringVariation1(dateString)){
                reformattedString = reformatDateStringVariation1(dateString)
                return reformattedString
            }
            else{
                reformattedString = reformatDatestring(dateString)
                return reformattedString
            }
        }
    
        if("PY" in zoteroItem){
            dateString = zoteroItem["PY"] // this should just be a year
            reformattedString = reformatDateString(dateString)
            return reformattedString
        }
    
        return ""
    }
    catch(error)
    {
        return ""
    }
}

function getDescription(zoteroItem){
    primaryDescription = ""

    if("DA" in zoteroItem){
        primaryDescription = zoteroItem["AB"]
    }
    else if("PY" in zoteroItem){
        primaryDescription = zoteroItem["AB"]
    }

    formattedRisFields = ""
    for (const [key, value] of Object.entries(zoteroItem)) {
        formattedRisFields = formattedRisFields + `${key}: ${value}<br>`;
    }

    if(primaryDescription)
        return primaryDescription + "<p>&nbsp;</p><p>&nbsp;</p>" + formattedRisFields
    else
        return formattedRisFields
}

function getMediaFilesListedInTheZoteroManifest(zoteroList){
    expectedMediaFiles = []
    for(i = 0; i < zoteroList.length; i++){
        mediaForZoteroItem = getMediaFileFromZoteroItem(zoteroList[i])
        if(mediaForZoteroItem){
            expectedMediaFiles.push(mediaForZoteroItem)
        }
    }

    return expectedMediaFiles
}

function getTitle(zoteroItem){
    // bulletin propertes title, title_ar, sjac_title, sjac_title_ar, discovery_file_name, status, source_link can be a max length of 255 characters. They will be truncated, here
    // it looks like the Media title property is not size-limited in the same way
    title = zoteroItem["TI"].substring(0, 255)
    if(title)
        return title
    else
        return ""
}

function getMediaTitle(zoteroItem){
    title = zoteroItem["TI"]
    return title
}

function getMediaFileFromZoteroItem(zoteroItem){
    return zoteroItem["L2"]
}

function getMediaFromZoteroItem(zoteroItem, mediaFilePath){
    // to debug errors in the DB saves, you have to explicitly pass show_exceptions = true for the model.save() calls, otherwise the exceptions are swallowed...
    // the definition for this json object does NOT match the database object. JSON properties are mapped from what is shown here to the DB/SQLAlchemy representation in Media to_json
    media = {
        title: getMediaTitle(zoteroItem),
        filename: mediaFilePath, //media_file in the db
        fileType: "", // media_file_type
    }

    return media
}

function getPrimaryRecordWithMediaFromZoteroItem(zoteroItem, mediaFilePath, roles, incident_relations){
    media = getMediaFromZoteroItem(zoteroItem, mediaFilePath)

    bulletin = {
        title: getTitle(zoteroItem),
        status: 'Machine Created',
        description: getDescription(zoteroItem),
        // related events
        events: [],
        // related media
        medias: [media],
        // related bulletins
        bulletin_relations: [],
        // related actors
        actor_relations: [],
        // related incidents
        incident_relations: incident_relations,
        bulletin_to_consent_uses: [],
        publish_date: getPublishDate(zoteroItem),
        created_at: '',
        discovery_file_name: '',
        roles: roles
    }

    return bulletin
}

function getPrimaryRecordWithoutMediaFromZoteroItem(zoteroItem, roles, incident_relations){
    bulletin = {
        title: getTitle(zoteroItem),
        status: 'Machine Created',
        description: getDescription(zoteroItem),
        // related events
        events: [],
        // related media
        medias: [],
        // related bulletins
        bulletin_relations: [],
        // related actors
        actor_relations: [],
        // related incidents
        incident_relations: incident_relations,
        bulletin_to_consent_uses: [],
        publish_date: getPublishDate(zoteroItem),
        created_at: '',
        discovery_file_name: '',
        roles: roles
    }

    return bulletin
}